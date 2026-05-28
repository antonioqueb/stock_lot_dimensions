# models/utils/picking_cleaner.py
# -*- coding: utf-8 -*-
"""
Utilidades para limpieza de lotes automáticos en pickings
"""
import logging

_logger = logging.getLogger(__name__)


class PickingLotCleaner:
    """Maneja la limpieza de lotes asignados automáticamente en pickings"""
    
    def __init__(self, env):
        self.env = env
        self._move_line_model = env['stock.move.line']
        self._move_model = env['stock.move']
        self._picking_model = env['stock.picking']

    def clear_pickings_lots(self, pickings, protected_lot_ids=None):
        """
        Elimina lotes automáticos de múltiples pickings
        
        Args:
            pickings: recordset de stock.picking
            protected_lot_ids: lista de lot IDs que NO deben ser eliminados
        """
        if not pickings:
            return
        
        # NUEVO: Si el contexto indica que no debemos limpiar, salir
        if self.env.context.get('skip_picking_clean'):
            _logger.info("Limpieza de pickings omitida por contexto skip_picking_clean")
            return
            
        _logger.info("Limpiando lotes automáticos de %d pickings", len(pickings))
        
        for picking in pickings:
            self._clear_single_picking(picking, protected_lot_ids)

    def _clear_single_picking(self, picking, protected_lot_ids=None):
        """Limpia un picking individual"""
        move_lines = self._get_clearable_move_lines(picking, protected_lot_ids)
        
        if not move_lines:
            return
            
        if self._delete_move_lines(move_lines, picking.name):
            self._reset_picking_state(picking)
            self._reset_moves_state(picking)
            self._invalidate_cache()

    def _get_clearable_move_lines(self, picking, protected_lot_ids=None):
        """Obtiene move_lines que pueden ser eliminadas"""
        domain = [
            ('picking_id', '=', picking.id),
            ('state', 'not in', ['done', 'cancel'])
        ]
        
        # NUEVO: Excluir lotes protegidos
        if protected_lot_ids:
            domain.append(('lot_id', 'not in', protected_lot_ids))
            _logger.info("Protegiendo lotes: %s", protected_lot_ids)
        
        return self._move_line_model.search(domain)

    def _delete_move_lines(self, move_lines, picking_name):
        """
        Elimina move_lines con manejo de errores.

        Importante:
        Para líneas reservadas no basta con unlink(). En Odoo la reserva física
        vive en stock.quant.reserved_quantity; borrar la línea sin desreservar
        puede dejar cantidades huérfanas. Por eso primero se ejecuta
        _do_unreserve() sobre los movimientos donde todas las líneas vivas son
        limpiables y después se elimina cualquier remanente.

        Returns:
            bool: True si se eliminaron exitosamente
        """
        try:
            count = len(move_lines)
            self._unreserve_moves_for_lines(move_lines)

            remaining_lines = move_lines.exists()
            if remaining_lines:
                remaining_lines.with_context(
                    skip_duplicate_lot_validation=True,
                    skip_hold_validation=True,
                    stone_transient_auto_assign_cleanup=True,
                ).unlink()

            _logger.info(
                "Eliminadas/desreservadas %d move_lines del picking %s",
                count,
                picking_name,
            )
            return True
        except Exception as e:
            _logger.error(
                "Error eliminando/desreservando move_lines del picking %s: %s",
                picking_name,
                str(e),
            )
            return False

    def _unreserve_moves_for_lines(self, move_lines):
        """
        Libera reservas de stock.quant antes de borrar líneas automáticas.

        Solo se llama _do_unreserve() cuando todas las líneas activas del move
        están dentro del conjunto limpiable. Así no se rompen líneas protegidas
        por protected_lot_ids ni selecciones manuales que deban sobrevivir.
        """
        if not move_lines:
            return

        clearable_ids = set(move_lines.ids)
        moves_to_unreserve = self._move_model.browse()

        for move in move_lines.mapped('move_id'):
            active_lines = move.move_line_ids.filtered(
                lambda ml: ml.state not in ('done', 'cancel')
            )
            if active_lines and set(active_lines.ids).issubset(clearable_ids):
                moves_to_unreserve |= move

        if not moves_to_unreserve:
            return

        _logger.info(
            "Desreservando %d move(s) antes de limpiar lotes automáticos: %s",
            len(moves_to_unreserve),
            moves_to_unreserve.ids,
        )

        moves_to_unreserve.with_context(
            skip_duplicate_lot_validation=True,
            skip_hold_validation=True,
            stone_transient_auto_assign_cleanup=True,
        )._do_unreserve()

    def _reset_picking_state(self, picking):
        """Resetea el estado del picking de 'assigned' a 'confirmed'"""
        if picking.state != 'assigned':
            return
            
        try:
            picking.write({'state': 'confirmed'})
        except Exception as e:
            _logger.warning("No se pudo resetear estado del picking %s: %s", 
                          picking.name, str(e))

    def _reset_moves_state(self, picking):
        """Resetea el estado de los moves de 'assigned' a 'confirmed'"""
        moves_to_reset = picking.move_ids.filtered(lambda m: m.state == 'assigned')
        
        if not moves_to_reset:
            return
            
        try:
            moves_to_reset.write({'state': 'confirmed'})
        except Exception as e:
            _logger.warning("Error reseteando moves del picking %s: %s", 
                          picking.name, str(e))

    def _invalidate_cache(self):
        """Invalida caché de modelos de stock"""
        self._move_line_model.invalidate_model()
        self._move_model.invalidate_model()
        self._picking_model.invalidate_model()