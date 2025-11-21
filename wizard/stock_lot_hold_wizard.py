# ./wizard/stock_lot_hold_wizard.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta

class StockLotHoldWizard(models.TransientModel):
    _name = 'stock.lot.hold.wizard'
    _description = 'Wizard para crear reservas manuales de lotes'

    quant_id = fields.Many2one(
        'stock.quant',
        string='Quant',
        required=True,
        readonly=True
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        readonly=True
    )
    
    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        related='lot_id.product_id',
        readonly=True
    )
    
    ubicacion_id = fields.Many2one(
        'stock.location',
        string='Ubicación',
        related='quant_id.location_id',
        readonly=True
    )
    
    cantidad_disponible = fields.Float(
        string='Cantidad Disponible',
        related='quant_id.available_quantity',
        readonly=True
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        default=lambda self: self.env.user,
        readonly=True,
        required=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        help='Cliente para quien se reserva el lote'
    )
    
    project_id = fields.Many2one(
        'project.project',
        string='Proyecto',
        help='Proyecto al que pertenece esta reserva'
    )
    
    project_name = fields.Char(
        string='Nombre del Proyecto',
        help='Ingrese el nombre del nuevo proyecto'
    )
    
    arquitecto_id = fields.Many2one(
        'res.partner',
        string='Arquitecto',
        domain=[('x_es_arquitecto', '=', True)],
        help='Arquitecto responsable del proyecto'
    )
    
    arquitecto_name = fields.Char(
        string='Nombre del Arquitecto',
        help='Ingrese el nombre del nuevo arquitecto'
    )
    
    fecha_expiracion = fields.Datetime(
        string='Expira el',
        compute='_compute_fecha_expiracion',
        readonly=True,
        help='Fecha de expiración (5 días hábiles desde hoy)'
    )
    
    notas = fields.Text(
        string='Notas'
    )
    
    x_grosor = fields.Float(related='lot_id.x_grosor', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', readonly=True)
    x_atado = fields.Char(related='lot_id.x_atado', readonly=True)
    x_tipo = fields.Selection(related='lot_id.x_tipo', readonly=True)

    def _calcular_dias_habiles(self, fecha_inicio, dias_habiles):
        """Calcular fecha de expiración sumando días hábiles"""
        fecha_actual = fecha_inicio
        dias_agregados = 0
        
        while dias_agregados < dias_habiles:
            fecha_actual += timedelta(days=1)
            if fecha_actual.weekday() < 5:  # 0-4 = lunes a viernes
                dias_agregados += 1
        
        return fecha_actual

    @api.depends('create_date')
    def _compute_fecha_expiracion(self):
        """Calcular fecha de expiración: 5 días hábiles desde hoy"""
        for record in self:
            record.fecha_expiracion = self._calcular_dias_habiles(fields.Datetime.now(), 5)

    @api.onchange('project_name')
    def _onchange_project_name(self):
        if self.project_name:
            self.project_id = False

    @api.onchange('arquitecto_name')
    def _onchange_arquitecto_name(self):
        if self.arquitecto_name:
            self.arquitecto_id = False

    @api.constrains('project_id', 'project_name')
    def _check_project(self):
        for record in self:
            if not record.project_id and not record.project_name:
                raise ValidationError('Debe seleccionar un proyecto existente o ingresar el nombre de uno nuevo.')

    @api.constrains('arquitecto_id', 'arquitecto_name')
    def _check_arquitecto(self):
        for record in self:
            if not record.arquitecto_id and not record.arquitecto_name:
                raise ValidationError('Debe seleccionar un arquitecto existente o ingresar el nombre de uno nuevo.')

    def action_crear_hold(self):
        """Crear una nueva reserva manual"""
        self.ensure_one()
        
        # Verificar hold existente
        hold_existente = self.env['stock.lot.hold'].search([
            ('quant_id', '=', self.quant_id.id),
            ('estado', '=', 'activo')
        ], limit=1)
        
        if hold_existente:
            raise UserError(
                f'Este lote ya tiene una reserva activa para {hold_existente.partner_id.name} '
                f'que expira el {hold_existente.fecha_expiracion.strftime("%d/%m/%Y")}'
            )
        
        # Obtener o crear proyecto
        project_id = self.project_id.id
        if self.project_name:
            project = self.env['project.project'].create({
                'name': self.project_name,
                'x_es_proyecto_marmol': True,
            })
            project_id = project.id
        
        # Obtener o crear arquitecto
        arquitecto_id = self.arquitecto_id.id
        if self.arquitecto_name:
            arquitecto = self.env['res.partner'].create({
                'name': self.arquitecto_name,
                'x_es_arquitecto': True,
                'company_type': 'person',
            })
            arquitecto_id = arquitecto.id
        
        # 🔑 CALCULAR fecha_expiracion ANTES de crear
        fecha_inicio = fields.Datetime.now()
        fecha_expiracion = self._calcular_dias_habiles(fecha_inicio, 5)
        
        # Crear el hold CON fecha_expiracion
        hold = self.env['stock.lot.hold'].create({
            'lot_id': self.lot_id.id,
            'quant_id': self.quant_id.id,
            'partner_id': self.partner_id.id,
            'user_id': self.user_id.id,
            'project_id': project_id,
            'arquitecto_id': arquitecto_id,
            'fecha_inicio': fecha_inicio,
            'fecha_expiracion': fecha_expiracion,
            'notas': self.notas,
        })
        
        # Mensaje de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '¡Reserva Creada!',
                'message': f'Lote {self.lot_id.name} reservado para {self.partner_id.name} por 5 días hábiles hasta el {hold.fecha_expiracion.strftime("%d/%m/%Y %H:%M")}',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }