# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    def action_assign(self):
        """Override para filtrar quants con hold al reservar"""
        _logger.info("🟢 [STOCK PICKING] action_assign() llamado para picking: %s", self.mapped('name'))
        
        for picking in self:
            if picking.picking_type_code == 'outgoing' and picking.partner_id:
                # Pasar el cliente permitido en el contexto
                self = self.with_context(allowed_partner_id=picking.partner_id.id)
        
        result = super(StockPicking, self).action_assign()
        _logger.info("🟢 [STOCK PICKING] action_assign() completado")
        return result
    
    def _action_assign(self):
        """
        Override para limpiar lotes automáticos después de la asignación
        Este método se ejecuta cuando Odoo asigna/reserva inventario automáticamente
        """
        _logger.info("="*80)
        _logger.info("🟡 [STOCK PICKING] _action_assign() INICIANDO para picking(s): %s", self.mapped('name'))
        
        # Ejecutar el proceso normal de asignación (esto crea los lotes automáticamente)
        res = super(StockPicking, self)._action_assign()
        _logger.info("🟡 [STOCK PICKING] Super _action_assign() completado")
        
        # Después de la asignación, limpiar TODOS los lotes que se asignaron automáticamente
        for picking in self:
            _logger.info("🟡 [STOCK PICKING] Procesando picking: %s (ID: %s)", picking.name, picking.id)
            _logger.info("🟡 [STOCK PICKING] Sale Order: %s", picking.sale_id.name if picking.sale_id else 'No tiene sale_id')
            _logger.info("🟡 [STOCK PICKING] Picking Type: %s", picking.picking_type_code)
            
            # Verificar si este picking viene de una orden de venta
            if picking.sale_id:
                _logger.info("🟡 [STOCK PICKING] ✅ Picking viene de Sale Order - procediendo a limpiar lotes")
                
                # Buscar todas las stock.move.line de este picking
                move_lines = self.env['stock.move.line'].search([
                    ('picking_id', '=', picking.id)
                ])
                
                _logger.info("🟡 [STOCK PICKING] Move lines encontradas: %s", len(move_lines))
                
                for ml in move_lines:
                    _logger.info("🟡 [STOCK PICKING]   - Move Line ID: %s, Lote: %s, Producto: %s, Cantidad: %s, Estado: %s", 
                                ml.id, 
                                ml.lot_id.name if ml.lot_id else 'Sin Lote',
                                ml.product_id.name, 
                                ml.quantity,
                                ml.state)
                
                # Limpiar los lotes de todas las líneas
                if move_lines:
                    _logger.info("🟡 [STOCK PICKING] ¡LIMPIANDO LOTES AHORA! Actualizando %s líneas...", len(move_lines))
                    
                    try:
                        move_lines.write({
                            'lot_id': False,
                            'lot_name': False,
                        })
                        _logger.info("🟡 [STOCK PICKING] ✅ Write ejecutado exitosamente")
                        
                        # Forzar commit para asegurar que se guardan los cambios
                        self.env.cr.commit()
                        _logger.info("🟡 [STOCK PICKING] ✅ Commit ejecutado")
                        
                        # Verificar que se limpiaron
                        move_lines_verificacion = self.env['stock.move.line'].search([
                            ('picking_id', '=', picking.id)
                        ])
                        _logger.info("🟡 [STOCK PICKING] VERIFICACIÓN - Total líneas: %s", len(move_lines_verificacion))
                        for ml in move_lines_verificacion:
                            _logger.info("🟡 [STOCK PICKING] VERIFICACIÓN - Move Line ID: %s, Lote después: %s", 
                                        ml.id, ml.lot_id.name if ml.lot_id else '✅ VACÍO')
                    except Exception as e:
                        _logger.error("🟡 [STOCK PICKING] ❌ ERROR al limpiar lotes: %s", str(e))
                        _logger.exception("🟡 [STOCK PICKING] Traceback completo:")
                else:
                    _logger.warning("🟡 [STOCK PICKING] ⚠️ No se encontraron move_lines para limpiar")
            else:
                _logger.info("🟡 [STOCK PICKING] ⏭️ Picking NO viene de Sale Order - saltando limpieza de lotes")
        
        _logger.info("🟡 [STOCK PICKING] _action_assign() FINALIZADO")
        _logger.info("="*80)
        return res
    
    def button_validate(self):
        """Validar holds antes de validar el picking"""
        _logger.info("🔴 [STOCK PICKING] button_validate() iniciando para: %s", self.mapped('name'))
        
        for picking in self:
            if picking.picking_type_code == 'outgoing':
                for move_line in picking.move_line_ids:
                    if move_line.lot_id:
                        _logger.info("🔴 [STOCK PICKING] Verificando lote: %s para move_line: %s", 
                                    move_line.lot_id.name, move_line.id)
                        
                        # Verificar si el lote tiene hold
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', move_line.lot_id.id),
                            ('location_id', '=', move_line.location_id.id),
                            ('x_tiene_hold', '=', True),
                        ], limit=1)
                        
                        if quant and quant.x_hold_activo_id:
                            # Validar que el cliente coincida
                            if picking.partner_id != quant.x_hold_activo_id.partner_id:
                                _logger.warning("🔴 [STOCK PICKING] ⚠️ Hold encontrado para cliente diferente")
                                raise UserError(
                                    f"🔒 NO PUEDE VALIDAR ESTA ENTREGA\n\n"
                                    f"El lote '{move_line.lot_id.name}' está RESERVADO para:\n"
                                    f"👤 {quant.x_hold_para}\n"
                                    f"📅 Hasta: {quant.x_hold_expira.strftime('%d/%m/%Y %H:%M')}\n"
                                    f"⏱️ Días restantes: {quant.x_hold_dias_restantes}\n\n"
                                    f"❌ Esta entrega es para '{picking.partner_id.name}'"
                                )
        
        result = super(StockPicking, self).button_validate()
        _logger.info("🔴 [STOCK PICKING] button_validate() completado")
        return result