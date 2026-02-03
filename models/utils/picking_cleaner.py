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
        Elimina move_lines con manejo de errores
        
        Returns:
            bool: True si se eliminaron exitosamente
        """
        try:
            count = len(move_lines)
            move_lines.unlink()
            _logger.info("Eliminadas %d move_lines del picking %s", count, picking_name)
            return True
        except Exception as e:
            _logger.error("Error eliminando move_lines del picking %s: %s", 
                         picking_name, str(e))
            return False

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