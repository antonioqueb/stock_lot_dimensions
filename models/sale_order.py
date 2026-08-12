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

    # MÁSCARA COMERCIAL — por VENTA, no por producto: el nombre con el que el
    # cliente conoce el material en ESTA operación (se vende "NEGRO SAN
    # GABRIEL" aunque el material real sea Santo Tomás). Nace en el quote, el
    # hold o la orden, se propaga en las conversiones y TODOS los documentos
    # (cotización, orden, entregas, pick tickets, remisiones, factura)
    # imprimen la máscara en lugar del nombre propio del material.
    x_mask_name = fields.Char(
        string='Máscara',
        copy=True,
        help='Nombre comercial del material para ESTA venta. Los documentos '
             'que genera el sistema imprimen la máscara en lugar del nombre '
             'real del producto. Se propaga de quote a hold y a la orden.',
    )

    def _som_default_line_description(self):
        self.ensure_one()
        try:
            return self._get_sale_order_line_multiline_description_sale()
        except Exception:
            return self.product_id.get_product_multiline_description_sale() \
                if self.product_id else (self.name or '')

    def _som_apply_mask_to_description(self, restore=False):
        """La descripción (name) es lo que imprimen los documentos estándar
        (cotización, factura, entregas): con máscara, la descripción ES la
        máscara; al quitarla, regresa la descripción comercial del producto.
        También se sincroniza description_picking de los movimientos vivos,
        que es lo que imprimen los documentos estándar de almacén."""
        for line in self:
            if line.display_type or not line.product_id:
                continue
            if line.x_mask_name:
                if (line.name or '') != line.x_mask_name:
                    line.name = line.x_mask_name
            elif restore:
                line.name = line._som_default_line_description()

            open_moves = line.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel'))
            if not open_moves:
                continue
            if line.x_mask_name:
                open_moves.write({'description_picking': line.x_mask_name})
            elif restore:
                for move in open_moves:
                    move.description_picking = move.product_id._get_description(
                        move.picking_type_id)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        masked = lines.filtered(lambda l: l.x_mask_name)
        if masked:
            masked._som_apply_mask_to_description()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'x_mask_name' in vals:
            # Escribir/limpiar la máscara re-sincroniza la descripción.
            self._som_apply_mask_to_description(restore=not vals.get('x_mask_name'))
        elif 'product_id' in vals:
            # Cambiar el producto recomputa la descripción con el nombre REAL:
            # la máscara debe volver a taparlo.
            self.filtered('x_mask_name')._som_apply_mask_to_description()
        return res


class StockMoveMask(models.Model):
    _inherit = 'stock.move'

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        # Movimientos que nacen DESPUÉS de escribir la máscara (entregas,
        # backorders): heredan el nombre comercial de la línea de venta para
        # que los documentos de almacén jamás muestren el nombre real.
        for move in moves:
            mask = move.sale_line_id.x_mask_name if move.sale_line_id else ''
            if mask and move.state not in ('done', 'cancel') \
                    and move.description_picking != mask:
                move.description_picking = mask
        return moves


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_project_id = fields.Many2one('project.project', string='Proyecto')
    x_architect_id = fields.Many2one('res.partner', string='Embajador')
    
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
        
        # Comparación por CLIENTE COMERCIAL (igual que el HoldValidator
        # canónico): un hold a nombre del contacto de compras y una venta a
        # nombre de la empresa madre son el mismo cliente — antes se comparaba
        # el partner exacto y se rechazaba la venta legítima.
        order_partner = self.env['res.partner'].browse(partner_id)
        order_commercial = order_partner.commercial_partner_id

        for product in products:
            for quant_id in product['selected_lots']:
                quant = self.env['stock.quant'].browse(quant_id)
                if quant.x_tiene_hold:
                    hold_partner = quant.x_hold_activo_id.partner_id
                    if hold_partner.commercial_partner_id != order_commercial:
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
            
            line_vals = {
                'order_id': sale_order.id,
                'product_id': product['product_id'],
                'product_uom_qty': product['quantity'],
                'price_unit': product['price_unit'],
                'tax_ids': tax_ids,
                'x_selected_lots': [(6, 0, product['selected_lots'])],
                'company_id': company_id,
            }
            # Máscara comercial (hold → SO): el nombre personalizado de la
            # venta viaja con la línea; el hook de create la aplica al name.
            if product.get('mask_name'):
                line_vals['x_mask_name'] = product['mask_name']

            self.env['sale.order.line'].with_company(company_id).create(line_vals)
        
        if services:
            for service in services:
                service_product = self.env['product.product'].browse(service['product_id'])
                
                if apply_tax and service_product.taxes_id:
                    tax_ids = [(6, 0, service_product.taxes_id.ids)]
                else:
                    tax_ids = [(5, 0, 0)]
                
                service_vals = {
                    'order_id': sale_order.id,
                    'product_id': service['product_id'],
                    'product_uom_qty': service['quantity'],
                    'price_unit': service['price_unit'],
                    'tax_ids': tax_ids,
                    'company_id': company_id,
                }
                if service.get('mask_name'):
                    service_vals['x_mask_name'] = service['mask_name']

                self.env['sale.order.line'].with_company(company_id).create(service_vals)
        
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