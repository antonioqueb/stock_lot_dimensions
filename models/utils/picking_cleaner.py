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
    
    def clear_pickings_lots(self, pickings):
        """
        Elimina lotes automáticos de múltiples pickings
        
        Args:
            pickings: recordset de stock.picking
        """
        if not pickings:
            return
        
        _logger.info("Limpiando lotes automáticos de %d pickings", len(pickings))
        
        for picking in pickings:
            self._clear_single_picking(picking)
    
    def _clear_single_picking(self, picking):
        """Limpia un picking individual"""
        move_lines = self._get_clearable_move_lines(picking)
        
        if not move_lines:
            return
        
        if self._delete_move_lines(move_lines, picking.name):
            self._reset_picking_state(picking)
            self._reset_moves_state(picking)
            self._invalidate_cache()
    
    def _get_clearable_move_lines(self, picking):
        """Obtiene move_lines que pueden ser eliminadas"""
        return self._move_line_model.search([
            ('picking_id', '=', picking.id),
            ('state', 'not in', ['done', 'cancel'])
        ])
    
    def _delete_move_lines(self, move_lines, picking_name):
        """
        Elimina move_lines con manejo de errores
        
        Returns:
            bool: True si se eliminaron exitosamente
        """
        try:
            move_lines.unlink()
            _logger.info("Eliminadas %d move_lines del picking %s", 
                        len(move_lines), picking_name)
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