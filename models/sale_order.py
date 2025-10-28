# -*- coding: utf-8 -*-
from odoo import models, fields, api

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
        # Primero ejecutar el proceso normal de confirmación
        res = super(SaleOrder, self).action_confirm()
        
        # Después de confirmar, limpiar los lotes de todas las líneas de movimiento
        for order in self:
            # Buscar todos los pickings relacionados con esta orden
            pickings = order.picking_ids
            
            for picking in pickings:
                # Iterar sobre todas las líneas de movimiento detalladas (move_line_ids)
                for move_line in picking.move_line_ids:
                    # Si la línea tiene un lote asignado automáticamente, limpiarlo
                    if move_line.lot_id:
                        move_line.write({
                            'lot_id': False,
                            'lot_name': False,
                        })
        
        return res