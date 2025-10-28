# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_assign(self):
        """Override para filtrar quants con hold al reservar"""
        for picking in self:
            if picking.picking_type_code == 'outgoing' and picking.partner_id:
                # Pasar el cliente permitido en el contexto
                self = self.with_context(allowed_partner_id=picking.partner_id.id)
        
        return super(StockPicking, self).action_assign()

    def button_validate(self):
        """Validar holds antes de validar el picking"""
        for picking in self:
            if picking.picking_type_code == 'outgoing':
                for move_line in picking.move_line_ids:
                    if move_line.lot_id:
                        # Verificar si el lote tiene hold
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', move_line.lot_id.id),
                            ('location_id', '=', move_line.location_id.id),
                            ('x_tiene_hold', '=', True),
                        ], limit=1)
                        
                        if quant and quant.x_hold_activo_id:
                            # Validar que el cliente coincida
                            if picking.partner_id != quant.x_hold_activo_id.partner_id:
                                raise UserError(
                                    f"🔒 NO PUEDE VALIDAR ESTA ENTREGA\n\n"
                                    f"El lote '{move_line.lot_id.name}' está RESERVADO para:\n"
                                    f"👤 {quant.x_hold_para}\n"
                                    f"📅 Hasta: {quant.x_hold_expira.strftime('%d/%m/%Y %H:%M')}\n"
                                    f"⏱️ Días restantes: {quant.x_hold_dias_restantes}\n\n"
                                    f"❌ Esta entrega es para '{picking.partner_id.name}'"
                                )
        
        return super(StockPicking, self).button_validate()