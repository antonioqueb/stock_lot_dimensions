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
    
    @api.model
    def create_from_shopping_cart(self, partner_id=None, products=None, services=None, notes=None, pricelist_id=None, apply_tax=True, project_id=None, architect_id=None):
        if not partner_id or not products:
            raise UserError("Faltan parámetros: partner_id o products")
        
        if not pricelist_id:
            raise UserError("Debe especificar una lista de precios")
        
        pricelist = self.env['product.pricelist'].browse(pricelist_id)
        currency_code = pricelist.name
        
        # Si viene de hold order, omitir verificación de autorización
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
        
        # Crear orden
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
        
        sale_order.with_company(company_id).action_confirm()
        
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
            move.move_line_ids.unlink()
            move_line_model = self.env['stock.move.line'].with_context(skip_hold_validation=True)
            
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
        self._clear_auto_assigned_lots()
        return res
    
    def _clear_auto_assigned_lots(self):
        cleaner = PickingLotCleaner(self.env)
        for order in self:
            if order.picking_ids:
                cleaner.clear_pickings_lots(order.picking_ids)

    @api.model
    def _update_email_template_report(self):
        """
        Función llamada desde XML (data/mail_template_summary.xml) para actualizar 
        la plantilla de correo y forzar el uso del reporte personalizado.
        Esto se hace vía Python para saltar la protección noupdate="1" del registro original.
        """
        # 1. Buscar la plantilla original de ventas
        template = self.env.ref('sale.email_template_edi_sale', raise_if_not_found=False)
        
        # 2. Buscar tu reporte personalizado
        report = self.env.ref('stock_lot_dimensions.action_report_sale_order_custom_summary', raise_if_not_found=False)
        
        if template and report:
            try:
                # 3. Forzar la escritura (Python ignora noupdate)
                # Usamos 'report_template_ids' que es el campo estándar en versiones recientes (Many2many)
                template.write({
                    'report_template_ids': [(6, 0, [report.id])],
                    'report_name': "Orden de Venta - {{ (object.name or '') }}"
                })
                _logger.info("SUCCESS: Plantilla de correo de ventas actualizada al reporte personalizado (stock_lot_dimensions).")
            except Exception as e:
                _logger.error(f"ERROR: No se pudo actualizar la plantilla de correo: {str(e)}")
        else:
            _logger.warning("WARNING: No se pudo actualizar la plantilla. Plantilla 'sale.email_template_edi_sale' o Reporte no encontrados.")