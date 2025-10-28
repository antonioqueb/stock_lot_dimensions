# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    # ✅ SIN VALIDACIONES
    # Puedes crear y confirmar órdenes de venta libremente
    # sin importar si hay lotes reservados o no
    pass

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def action_confirm(self):
        """
        Override del método action_confirm para limpiar lotes automáticos
        después de confirmar la orden de venta
        """
        _logger.info("="*80)
        _logger.info("🔵 [SALE ORDER] Iniciando action_confirm() para orden: %s", self.name)
        
        # Primero ejecutar el proceso normal de confirmación
        res = super(SaleOrder, self).action_confirm()
        _logger.info("🔵 [SALE ORDER] Super action_confirm() completado")
        
        # Después de confirmar, limpiar TODOS los lotes asignados automáticamente
        for order in self:
            _logger.info("🔵 [SALE ORDER] Procesando orden: %s", order.name)
            
            # Buscar todos los pickings relacionados con esta orden
            pickings = order.picking_ids
            _logger.info("🔵 [SALE ORDER] Pickings encontrados: %s (%s)", len(pickings), pickings.mapped('name'))
            
            for picking in pickings:
                _logger.info("🔵 [SALE ORDER] Procesando picking: %s (ID: %s)", picking.name, picking.id)
                
                # ============================================
                # SOLUCIÓN DEFINITIVA: ELIMINAR move_lines
                # ============================================
                # En lugar de solo limpiar los lotes, ELIMINAMOS las move_lines
                # Esto fuerza que cuando el usuario abra "Operaciones Detalladas"
                # no haya ninguna línea pre-creada con lotes
                
                move_lines_to_delete = self.env['stock.move.line'].search([
                    ('picking_id', '=', picking.id),
                    ('state', 'not in', ['done', 'cancel'])  # Solo las que no están finalizadas
                ])
                
                _logger.info("🔵 [SALE ORDER] Move lines encontradas para ELIMINAR: %s", len(move_lines_to_delete))
                
                if move_lines_to_delete:
                    for ml in move_lines_to_delete:
                        _logger.info("🔵 [SALE ORDER]   - Move Line ID: %s, Lote: %s, Producto: %s, Cantidad: %s", 
                                    ml.id, 
                                    ml.lot_id.name if ml.lot_id else 'Sin Lote',
                                    ml.product_id.name, 
                                    ml.quantity)
                    
                    try:
                        _logger.info("🔵 [SALE ORDER] ¡ELIMINANDO %s move lines!", len(move_lines_to_delete))
                        move_lines_to_delete.unlink()
                        _logger.info("🔵 [SALE ORDER] ✅ Move lines ELIMINADAS exitosamente")
                    except Exception as e:
                        _logger.error("🔵 [SALE ORDER] ❌ Error eliminando move_lines: %s", str(e))
                        _logger.exception("🔵 [SALE ORDER] Traceback:")
                else:
                    _logger.info("🔵 [SALE ORDER] No hay move_lines para eliminar")
                
                # ============================================
                # Resetear el estado del picking si es necesario
                # ============================================
                if picking.state == 'assigned':
                    _logger.info("🔵 [SALE ORDER] Picking está 'assigned' - cambiando a 'confirmed'")
                    try:
                        picking.write({'state': 'confirmed'})
                        _logger.info("🔵 [SALE ORDER] ✅ Picking state actualizado")
                    except Exception as e:
                        _logger.error("🔵 [SALE ORDER] ⚠️ No se pudo cambiar state del picking: %s", str(e))
                
                # ============================================
                # Resetear los moves también
                # ============================================
                for move in picking.move_ids:
                    if move.state == 'assigned':
                        _logger.info("🔵 [SALE ORDER] Move %s está 'assigned' - reseteando", move.id)
                        try:
                            move.write({'state': 'confirmed'})
                            _logger.info("🔵 [SALE ORDER] ✅ Move %s reseteado", move.id)
                        except Exception as e:
                            _logger.error("🔵 [SALE ORDER] ⚠️ Error reseteando move: %s", str(e))
                
                # ============================================
                # INVALIDAR CACHE para forzar recarga
                # ============================================
                self.env['stock.move.line'].invalidate_model()
                self.env['stock.move'].invalidate_model()
                self.env['stock.picking'].invalidate_model()
                _logger.info("🔵 [SALE ORDER] ✅ Cache invalidado")
                
                # Verificación final
                move_lines_verificacion = self.env['stock.move.line'].search([
                    ('picking_id', '=', picking.id)
                ])
                
                _logger.info("🔵 [SALE ORDER] ═══════════════════════════════════════════")
                _logger.info("🔵 [SALE ORDER] VERIFICACIÓN FINAL")
                _logger.info("🔵 [SALE ORDER] ═══════════════════════════════════════════")
                _logger.info("🔵 [SALE ORDER] Total move_lines después: %s", len(move_lines_verificacion))
                
                if move_lines_verificacion:
                    _logger.warning("🔵 [SALE ORDER] ⚠️ AÚN HAY MOVE LINES:")
                    for ml in move_lines_verificacion:
                        _logger.info("🔵 [SALE ORDER]   - Move Line ID: %s, Lote: %s, Estado: %s", 
                                    ml.id, 
                                    ml.lot_id.name if ml.lot_id else '✅ VACÍO',
                                    ml.state)
                else:
                    _logger.info("🔵 [SALE ORDER] ✅✅✅ PERFECTO - NO HAY MOVE LINES")
                    _logger.info("🔵 [SALE ORDER] ✅✅✅ Picking completamente limpio")
                
                _logger.info("🔵 [SALE ORDER] ═══════════════════════════════════════════")
        
        _logger.info("🔵 [SALE ORDER] action_confirm() finalizado")
        _logger.info("="*80)
        return res