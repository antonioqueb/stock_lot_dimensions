# -*- coding: utf-8 -*-
# models/stock_lot_hold_order.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from .utils.business_days import BusinessDaysCalculator

class StockLotHoldOrder(models.Model):
    _name = 'stock.lot.hold.order'
    _description = 'Orden de Reserva de Lotes'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(
        string='Número',
        required=True,
        readonly=True,
        default='/',
        copy=False
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        readonly=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        tracking=True
    )
    
    # NUEVO CAMPO
    delivery_address = fields.Text(
        string='Dirección de Entrega',
        tracking=True
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        default=lambda self: self.env.user,
        required=True,
        tracking=True
    )
    
    project_id = fields.Many2one(
        'project.project',
        string='Proyecto',
        tracking=True
    )
    
    arquitecto_id = fields.Many2one(
        'res.partner',
        string='Arquitecto',
        domain=[('x_es_arquitecto', '=', True)],
        tracking=True
    )
    
    fecha_orden = fields.Datetime(
        string='Fecha Orden',
        default=fields.Datetime.now,
        required=True,
        readonly=True
    )
    
    fecha_expiracion = fields.Datetime(
        string='Fecha Expiración',
        required=True,
        readonly=True
    )
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmada'),
        ('done', 'Finalizada'),
        ('cancel', 'Cancelada'),
    ], string='Estado', default='draft', required=True, tracking=True)
    
    hold_line_ids = fields.One2many(
        'stock.lot.hold.order.line',
        'order_id',
        string='Líneas de Reserva'
    )
    
    notas = fields.Text(string='Notas')
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True
    )
    
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta Generada',
        readonly=True,
        tracking=True
    )
    
    total_placas = fields.Integer(
        string='Total Placas',
        compute='_compute_totals',
        store=True
    )
    
    total_m2 = fields.Float(
        string='Total m²',
        compute='_compute_totals',
        store=True,
        digits=(10, 2)
    )
    
    total_con_precio = fields.Monetary(
        string='Total General',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    
    dias_restantes = fields.Integer(
        string='Días Restantes',
        compute='_compute_dias_restantes'
    )
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Actualiza dirección de entrega al cambiar cliente"""
        if self.partner_id:
            address_parts = []
            if self.partner_id.street:
                address_parts.append(self.partner_id.street)
            if self.partner_id.street2:
                address_parts.append(self.partner_id.street2)
            
            city_parts = []
            if self.partner_id.city:
                city_parts.append(self.partner_id.city)
            if self.partner_id.state_id:
                city_parts.append(self.partner_id.state_id.name)
            if self.partner_id.zip:
                city_parts.append(f"C.P. {self.partner_id.zip}")
            
            if city_parts:
                address_parts.append(', '.join(city_parts))
            
            if self.partner_id.country_id:
                address_parts.append(self.partner_id.country_id.name)
            
            self.delivery_address = '\n'.join(address_parts) if address_parts else ''
    
    @api.depends('hold_line_ids.cantidad_m2', 'hold_line_ids.precio_total')
    def _compute_totals(self):
        for order in self:
            order.total_placas = len(order.hold_line_ids)
            order.total_m2 = sum(order.hold_line_ids.mapped('cantidad_m2'))
            order.total_con_precio = sum(order.hold_line_ids.mapped('precio_total'))
    
    @api.depends('fecha_expiracion', 'state')
    def _compute_dias_restantes(self):
        ahora = fields.Datetime.now()
        for order in self:
            if order.state != 'confirmed' or not order.fecha_expiracion or order.fecha_expiracion <= ahora:
                order.dias_restantes = 0
            else:
                order.dias_restantes = BusinessDaysCalculator.count_business_days(ahora, order.fecha_expiracion)
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('stock.lot.hold.order') or '/'
            if 'fecha_expiracion' not in vals and vals.get('fecha_orden'):
                fecha_orden = fields.Datetime.to_datetime(vals['fecha_orden'])
                vals['fecha_expiracion'] = BusinessDaysCalculator.add_business_days(fecha_orden, 5)
        return super().create(vals_list)
    
    def action_confirm(self):
        for order in self:
            if not order.hold_line_ids:
                raise UserError('Debe agregar al menos una placa a la reserva.')
            for line in order.hold_line_ids:
                if line.hold_id:
                    continue
                
                notas_hold = f'Orden: {order.name}\n'
                if line.precio_unitario and line.currency_id:
                    notas_hold += f'Precio: {line.precio_unitario:.2f} {line.currency_id.name}/m²\n'
                    notas_hold += f'Total: {line.precio_total:.2f} {line.currency_id.name}\n'
                if order.notas:
                    notas_hold += f'\n{order.notas}'
                
                hold = self.env['stock.lot.hold'].create({
                    'lot_id': line.lot_id.id,
                    'quant_id': line.quant_id.id,
                    'partner_id': order.partner_id.id,
                    'user_id': order.user_id.id,
                    'project_id': order.project_id.id if order.project_id else False,
                    'arquitecto_id': order.arquitecto_id.id if order.arquitecto_id else False,
                    'fecha_inicio': order.fecha_orden,
                    'fecha_expiracion': order.fecha_expiracion,
                    'notas': notas_hold,
                    'company_id': order.company_id.id,
                })
                line.hold_id = hold.id
            order.state = 'confirmed'
    
    def action_cancel(self):
        for order in self:
            order.hold_line_ids.mapped('hold_id').filtered(lambda h: h.estado == 'activo').action_cancelar_hold()
            order.state = 'cancel'
    
    def action_done(self):
        self.state = 'done'
    
    def action_renew(self):
        for order in self:
            if order.state != 'confirmed':
                raise UserError('Solo puede renovar órdenes confirmadas.')
            order.hold_line_ids.mapped('hold_id').filtered(lambda h: h.estado == 'activo').action_renovar_hold()
            order.fecha_expiracion = BusinessDaysCalculator.get_expiration_date(days=5)
    
    def action_convert_to_sale_order(self):
        """Convierte la orden de reserva en orden de venta"""
        self.ensure_one()
        
        if self.state != 'confirmed':
            raise UserError('Solo puede convertir órdenes de reserva confirmadas.')
        
        if self.sale_order_id:
            raise UserError('Esta orden de reserva ya generó una orden de venta.')
        
        if not self.hold_line_ids:
            raise UserError('No hay líneas de reserva para convertir.')
        
        inactive_holds = self.hold_line_ids.filtered(lambda l: l.hold_id and l.hold_id.estado != 'activo')
        if inactive_holds:
            raise UserError('Hay reservas que ya no están activas. Renueve las reservas antes de convertir.')
        
        product_groups = {}
        for line in self.hold_line_ids:
            pid = line.product_id.id
            if pid not in product_groups:
                product_groups[pid] = {
                    'product_id': pid,
                    'quantity': 0,
                    'selected_lots': [],
                    'price_unit': line.precio_unitario or 0.0,
                }
            product_groups[pid]['quantity'] += line.cantidad_m2
            product_groups[pid]['selected_lots'].append(line.quant_id.id)
        
        products = list(product_groups.values())
        
        notes = f'=== CONVERTIDO DESDE ORDEN DE RESERVA ===\n'
        notes += f'Orden de Reserva: {self.name}\n'
        notes += f'Fecha de Reserva: {self.fecha_orden.strftime("%d/%m/%Y %H:%M")}\n'
        if self.project_id:
            notes += f'\n=== INFORMACIÓN DEL PROYECTO ===\n'
            notes += f'Proyecto: {self.project_id.name}\n'
        if self.arquitecto_id:
            notes += f'Arquitecto: {self.arquitecto_id.name}\n'
        if self.notas:
            notes += f'\n{self.notas}'
        
        pricelist = self.env['product.pricelist'].search([
            ('name', '=', self.currency_id.name)
        ], limit=1)
        
        if not pricelist:
            raise UserError(f'No se encontró lista de precios para {self.currency_id.name}')
        
        try:
            result = self.env['sale.order'].with_context(
                from_hold_order=True,
                hold_order_id=self.id
            ).create_from_shopping_cart(
                partner_id=self.partner_id.id,
                products=products,
                services=[],
                notes=notes,
                pricelist_id=pricelist.id,
                apply_tax=True,
                project_id=self.project_id.id if self.project_id else None,
                architect_id=self.arquitecto_id.id if self.arquitecto_id else None
            )
            
            if result.get('needs_authorization'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '⚠️ Autorización Requerida',
                        'message': result['message'],
                        'type': 'warning',
                        'sticky': True,
                    }
                }
            
            if result.get('success'):
                sale_order = self.env['sale.order'].browse(result['order_id'])
                
                self.write({
                    'sale_order_id': sale_order.id,
                    'state': 'done'
                })
                
                for line in self.hold_line_ids:
                    if line.hold_id and line.hold_id.estado == 'activo':
                        line.hold_id.action_cancelar_hold()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '✅ Orden de Venta Creada',
                        'message': f'Orden {sale_order.name} creada exitosamente',
                        'type': 'success',
                        'sticky': False,
                        'next': {
                            'type': 'ir.actions.act_window',
                            'res_model': 'sale.order',
                            'res_id': sale_order.id,
                            'views': [[False, 'form']],
                            'target': 'current',
                        }
                    }
                }
        except Exception as e:
            raise UserError(f'Error al crear orden de venta: {str(e)}')


class StockLotHoldOrderLine(models.Model):
    _name = 'stock.lot.hold.order.line'
    _description = 'Línea de Orden de Reserva'
    _order = 'id'
    
    order_id = fields.Many2one(
        'stock.lot.hold.order', 
        string='Orden', 
        required=True, 
        ondelete='cascade'
    )
    
    quant_id = fields.Many2one(
        'stock.quant', 
        string='Quant', 
        required=True
    )
    
    lot_id = fields.Many2one(
        'stock.lot', 
        string='Lote', 
        required=True
    )
    
    product_id = fields.Many2one(
        'product.product', 
        string='Producto', 
        related='lot_id.product_id', 
        store=True, 
        readonly=True
    )
    
    cantidad_m2 = fields.Float(
        string='Cantidad (m²)', 
        related='quant_id.quantity', 
        store=True, 
        readonly=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='order_id.currency_id',
        store=True,
        readonly=True
    )
    
    precio_unitario = fields.Monetary(
        string='Precio/m²',
        currency_field='currency_id',
        digits='Product Price'
    )
    
    precio_total = fields.Monetary(
        string='Total',
        compute='_compute_precio_total',
        store=True,
        currency_field='currency_id'
    )
    
    x_grosor = fields.Float(
        related='lot_id.x_grosor', 
        string='Grosor (cm)', 
        readonly=True
    )
    x_alto = fields.Float(
        related='lot_id.x_alto', 
        string='Alto (m)', 
        readonly=True
    )
    x_ancho = fields.Float(
        related='lot_id.x_ancho', 
        string='Ancho (m)', 
        readonly=True
    )
    x_bloque = fields.Char(
        related='lot_id.x_bloque', 
        string='Bloque', 
        readonly=True
    )
    x_tipo = fields.Selection(
        related='lot_id.x_tipo', 
        string='Tipo', 
        readonly=True
    )
    
    hold_id = fields.Many2one(
        'stock.lot.hold', 
        string='Hold Creado', 
        readonly=True
    )
    
    @api.depends('cantidad_m2', 'precio_unitario')
    def _compute_precio_total(self):
        for line in self:
            if line.cantidad_m2 and line.precio_unitario:
                line.precio_total = line.cantidad_m2 * line.precio_unitario
            else:
                line.precio_total = 0.0
    
    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        if self.lot_id:
            domain = [
                ('lot_id', '=', self.lot_id.id),
                ('quantity', '>', 0),
                ('location_id.usage', '=', 'internal')
            ]
            if self.order_id and self.order_id.company_id:
                domain.append(('company_id', '=', self.order_id.company_id.id))
            
            quant = self.env['stock.quant'].search(domain, limit=1)
            
            if quant:
                self.quant_id = quant.id
            else:
                return {
                    'warning': {
                        'title': 'Advertencia', 
                        'message': f'No se encontró stock disponible para el lote {self.lot_id.name}'
                    }
                }