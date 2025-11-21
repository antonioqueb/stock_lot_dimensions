# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

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
        tracking=True,
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}
    )
    
    project_id = fields.Many2one(
        'project.project',
        string='Proyecto',
        tracking=True,
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}
    )
    
    arquitecto_id = fields.Many2one(
        'res.partner',
        string='Arquitecto',
        domain=[('x_es_arquitecto', '=', True)],
        tracking=True,
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}
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
        string='Líneas de Reserva',
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}
    )
    
    notas = fields.Text(
        string='Notas',
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}
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
    
    dias_restantes = fields.Integer(
        string='Días Restantes',
        compute='_compute_dias_restantes'
    )
    
    @api.depends('hold_line_ids.cantidad_m2')
    def _compute_totals(self):
        for order in self:
            order.total_placas = len(order.hold_line_ids)
            order.total_m2 = sum(order.hold_line_ids.mapped('cantidad_m2'))
    
    @api.depends('fecha_expiracion', 'state')
    def _compute_dias_restantes(self):
        from .utils.business_days import BusinessDaysCalculator
        ahora = fields.Datetime.now()
        
        for order in self:
            if order.state not in ['confirmed'] or order.fecha_expiracion <= ahora:
                order.dias_restantes = 0
            else:
                order.dias_restantes = BusinessDaysCalculator.count_business_days(
                    ahora, 
                    order.fecha_expiracion
                )
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('stock.lot.hold.order') or '/'
            
            if 'fecha_expiracion' not in vals and vals.get('fecha_orden'):
                from .utils.business_days import BusinessDaysCalculator
                fecha_orden = fields.Datetime.to_datetime(vals['fecha_orden'])
                vals['fecha_expiracion'] = BusinessDaysCalculator.add_business_days(fecha_orden, 5)
        
        return super().create(vals_list)
    
    def action_confirm(self):
        """Confirmar y crear holds individuales"""
        for order in self:
            if not order.hold_line_ids:
                raise UserError('Debe agregar al menos una placa a la reserva.')
            
            for line in order.hold_line_ids:
                if line.hold_id:
                    continue
                    
                hold = self.env['stock.lot.hold'].create({
                    'lot_id': line.lot_id.id,
                    'quant_id': line.quant_id.id,
                    'partner_id': order.partner_id.id,
                    'user_id': order.user_id.id,
                    'project_id': order.project_id.id if order.project_id else False,
                    'arquitecto_id': order.arquitecto_id.id if order.arquitecto_id else False,
                    'fecha_inicio': order.fecha_orden,
                    'fecha_expiracion': order.fecha_expiracion,
                    'notas': f'Orden: {order.name}\n{order.notas or ""}',
                })
                line.hold_id = hold.id
            
            order.state = 'confirmed'
    
    def action_cancel(self):
        """Cancelar orden y holds asociados"""
        for order in self:
            order.hold_line_ids.mapped('hold_id').filtered(
                lambda h: h.estado == 'activo'
            ).action_cancelar_hold()
            order.state = 'cancel'
    
    def action_done(self):
        """Finalizar orden"""
        self.state = 'done'
    
    def action_renew(self):
        """Renovar reserva por 5 días más"""
        for order in self:
            if order.state != 'confirmed':
                raise UserError('Solo puede renovar órdenes confirmadas.')
            
            order.hold_line_ids.mapped('hold_id').filtered(
                lambda h: h.estado == 'activo'
            ).action_renovar_hold()
            
            from .utils.business_days import BusinessDaysCalculator
            order.fecha_expiracion = BusinessDaysCalculator.get_expiration_date(days=5)


class StockLotHoldOrderLine(models.Model):
    _name = 'stock.lot.hold.order.line'
    _description = 'Línea de Orden de Reserva'
    _order = 'sequence, id'
    
    sequence = fields.Integer(
        string='Secuencia', 
        default=10,
        help='Orden de las líneas en la orden de reserva'
    )
    
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
    
    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        """Cargar quant_id cuando se selecciona un lote"""
        if self.lot_id:
            # Buscar quant disponible para este lote
            quant = self.env['stock.quant'].search([
                ('lot_id', '=', self.lot_id.id),
                ('quantity', '>', 0),
                ('location_id.usage', '=', 'internal')
            ], limit=1)
            
            if quant:
                self.quant_id = quant.id
            else:
                return {
                    'warning': {
                        'title': 'Advertencia',
                        'message': f'No se encontró stock disponible para el lote {self.lot_id.name}'
                    }
                }