# -*- coding: utf-8 -*-
# models/sale_order.py
from odoo import models, fields, api
from odoo.exceptions import UserError
from .utils.picking_cleaner import PickingLotCleaner
import logging

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    x_selected_lots = fields.Many2many('stock.quant', string='Lotes Seleccionados')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_project_id = fields.Many2one('project.project', string='Proyecto')
    x_architect_id = fields.Many2one('res.partner', string='Arquitecto')
    
    @api.model
    def create_from_shopping_cart(self, partner_id=None, products=None, services=None, notes=None, pricelist_id=None, apply_tax=True, project_id=None, architect_id=None):
        if not partner_id or not products:
            raise UserError("Faltan parámetros: partner_id o products")
        
        if not pricelist_id:
            raise UserError("Debe especificar una lista de precios")
        
        pricelist = self.env['product.pricelist'].browse(pricelist_id)
        currency_code = pricelist.name
        
        from_hold_order = self.env.context.get('from_hold_order', False)
        
        if not from_hold_order:
            product_prices = {}
            for product in products:
                product_prices[str(product['product_id'])] = product['price_unit']
            
            auth_check = self.env['product.template'].check_price_authorization_needed(
                product_prices, 
                currency_code
            )
            
            if auth_check['needs_authorization']:
                product_groups = {}
                for product in products:
                    pid = product['product_id']
                    if pid not in product_groups:
                        product_rec = self.env['product.product'].browse(pid)
                        product_groups[pid] = {
                            'name': product_rec.display_name,
                            'lots': [],
                            'total_quantity': 0
                        }
                    
                    for quant_id in product['selected_lots']:
                        quant = self.env['stock.quant'].browse(quant_id)
                        product_groups[pid]['lots'].append({
                            'id': quant_id,
                            'lot_name': quant.lot_id.name,
                            'quantity': quant.quantity
                        })
                        product_groups[pid]['total_quantity'] += quant.quantity
                
                result = self.env['stock.quant'].create_price_authorization(
                    operation_type='sale',
                    partner_id=partner_id,
                    project_id=project_id,
                    selected_lots=[q_id for p in products for q_id in p['selected_lots']],
                    currency_code=currency_code,
                    product_prices=product_prices,
                    product_groups=product_groups,
                    notes=notes,
                    architect_id=architect_id
                )
                
                if result['success']:
                    return {
                        'success': False,
                        'needs_authorization': True,
                        'authorization_id': result['authorization_id'],
                        'authorization_name': result['authorization_name'],
                        'message': f'Solicitud de autorización {result["authorization_name"]} creada. Espere aprobación del autorizador.'
                    }
        
        company_id = self.env.context.get('company_id') or self.env.company.id
        
        for product in products:
            for quant_id in product['selected_lots']:
                quant = self.env['stock.quant'].browse(quant_id)
                if quant.x_tiene_hold:
                    hold_partner = quant.x_hold_activo_id.partner_id
                    if hold_partner.id != partner_id:
                        raise UserError(f"El lote {quant.lot_id.name} está apartado para {hold_partner.name}")
        
        sale_order = self.with_company(company_id).create({
            'partner_id': partner_id,
            'note': notes or '',
            'pricelist_id': pricelist_id,
            'company_id': company_id,
        })
        
        for product in products:
            product_rec = self.env['product.product'].browse(product['product_id'])
            
            if apply_tax and product_rec.taxes_id:
                tax_ids = [(6, 0, product_rec.taxes_id.ids)]
            else:
                tax_ids = [(5, 0, 0)]
            
            self.env['sale.order.line'].with_company(company_id).create({
                'order_id': sale_order.id,
                'product_id': product['product_id'],
                'product_uom_qty': product['quantity'],
                'price_unit': product['price_unit'],
                'tax_ids': tax_ids,
                'x_selected_lots': [(6, 0, product['selected_lots'])],
                'company_id': company_id,
            })
        
        if services:
            for service in services:
                service_product = self.env['product.product'].browse(service['product_id'])
                
                if apply_tax and service_product.taxes_id:
                    tax_ids = [(6, 0, service_product.taxes_id.ids)]
                else:
                    tax_ids = [(5, 0, 0)]
                
                self.env['sale.order.line'].with_company(company_id).create({
                    'order_id': sale_order.id,
                    'product_id': service['product_id'],
                    'product_uom_qty': service['quantity'],
                    'price_unit': service['price_unit'],
                    'tax_ids': tax_ids,
                    'company_id': company_id,
                })
        
        sale_order.with_company(company_id).with_context(
            stone_transient_auto_assign=True,
            skip_duplicate_lot_validation=True,
            skip_hold_validation=True,
            skip_picking_clean=False,
        ).action_confirm()
        
        for line in sale_order.order_line:
            if line.x_selected_lots:
                picking = line.move_ids.mapped('picking_id')
                if picking:
                    self._assign_specific_lots(picking, line.product_id, line.x_selected_lots)
        
        if not from_hold_order:
            self.env['shopping.cart'].clear_cart()
        
        return {
            'success': True,
            'order_id': sale_order.id,
            'order_name': sale_order.name
        }
    
    def _assign_specific_lots(self, picking, product, quants):
        for move in picking.move_ids.filtered(lambda m: m.product_id == product):
            if move.move_line_ids:
                # Primero liberar la reserva nativa. Un unlink directo puede dejar
                # stock.quant.reserved_quantity inflado y provocar duplicidades en
                # la siguiente asignación exacta.
                move.with_context(
                    skip_duplicate_lot_validation=True,
                    skip_hold_validation=True,
                    stone_transient_auto_assign_cleanup=True,
                )._do_unreserve()

                remaining_lines = move.move_line_ids.exists()
                if remaining_lines:
                    remaining_lines.with_context(
                        skip_duplicate_lot_validation=True,
                        skip_hold_validation=True,
                        stone_transient_auto_assign_cleanup=True,
                    ).unlink()

            move_line_model = self.env['stock.move.line'].with_context(
                skip_hold_validation=True,
            )
            
            for quant in quants:
                move_line_model.create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': product.id,
                    'lot_id': quant.lot_id.id,
                    'location_id': quant.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'quantity': quant.quantity,
                    'product_uom_id': move.product_uom.id,
                })
    
    def action_confirm(self):
        _logger.info("Confirmando órdenes: %s", self.mapped('name'))
        
        all_partner_ids = self.mapped('partner_id.id')
        context = dict(self.env.context)
        if all_partner_ids:
            if len(all_partner_ids) == 1:
                context['allowed_partner_id'] = all_partner_ids[0]
            else:
                context['allowed_partner_ids'] = all_partner_ids
        
        res = super(SaleOrder, self.with_context(**context)).action_confirm()
        
        # MODIFICADO: Solo limpiar si NO viene de sale_stone_selection
        if not self.env.context.get('skip_picking_clean'):
            self._clear_auto_assigned_lots()
        else:
            _logger.info("[STONE] Limpieza de lotes omitida por contexto skip_picking_clean")
        
        return res
    
    def _clear_auto_assigned_lots(self):
        # MODIFICADO: Obtener lotes protegidos del contexto
        protected_lot_ids = self.env.context.get('protected_lot_ids', [])
        
        cleaner = PickingLotCleaner(self.env)
        for order in self:
            if order.picking_ids:
                cleaner.clear_pickings_lots(order.picking_ids, protected_lot_ids=protected_lot_ids)