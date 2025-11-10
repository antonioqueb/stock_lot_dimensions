# -*- coding: utf-8 -*-
# models/stock_lot_hold.py
from odoo import models, fields, api
from odoo.exceptions import UserError
from .utils.business_days import BusinessDaysCalculator
from .utils.notification_builder import NotificationBuilder
import logging

_logger = logging.getLogger(__name__)


class StockLotHold(models.Model):
    _name = 'stock.lot.hold'
    _description = 'Reservas Manuales de Lotes'
    _order = 'fecha_inicio desc'
    
    # ==================== CAMPOS BÁSICOS ====================
    name = fields.Char(
        string='Referencia',
        compute='_compute_name',
        store=True
    )
    
    quant_id = fields.Many2one(
        'stock.quant',
        string='Quant',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        readonly=True,
        index=True
    )
    
    # ==================== CAMPOS RELACIONADOS ====================
    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        related='lot_id.product_id',
        store=True,
        readonly=True
    )
    
    ubicacion_id = fields.Many2one(
        'stock.location',
        string='Ubicación',
        related='quant_id.location_id',
        store=True,
        readonly=True
    )
    
    # ==================== CAMPOS DE RESERVA ====================
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        readonly=True,
        index=True
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        required=True,
        readonly=True,
        index=True
    )
    
    project_id = fields.Many2one(
        'project.project',
        string='Proyecto',
        readonly=True
    )
    
    arquitecto_id = fields.Many2one(
        'res.partner',
        string='Arquitecto',
        readonly=True
    )
    
    # ==================== CAMPOS DE FECHAS ====================
    fecha_inicio = fields.Datetime(
        string='Fecha Inicio',
        default=fields.Datetime.now,
        required=True,
        readonly=True
    )
    
    fecha_expiracion = fields.Datetime(
        string='Fecha Expiración',
        required=True,
        readonly=True
    )
    
    # ==================== CAMPOS DE ESTADO ====================
    estado = fields.Selection(
        [
            ('activo', 'Activo'),
            ('expirado', 'Expirado'),
            ('cancelado', 'Cancelado'),
        ],
        string='Estado',
        default='activo',
        required=True,
        index=True
    )
    
    notas = fields.Text(string='Notas')
    
    dias_restantes = fields.Integer(
        string='Días Hábiles Restantes',
        compute='_compute_dias_restantes'
    )
    
    # ==================== MÉTODOS COMPUTADOS ====================
    @api.depends('lot_id', 'partner_id')
    def _compute_name(self):
        """Genera referencia del hold"""
        for record in self:
            if record.lot_id and record.partner_id:
                record.name = f"{record.lot_id.name} - {record.partner_id.name}"
            else:
                record.name = "Hold"
    
    @api.depends('fecha_expiracion', 'estado')
    def _compute_dias_restantes(self):
        """Calcula días hábiles restantes hasta expiración"""
        ahora = fields.Datetime.now()
        
        for record in self:
            if record.estado != 'activo' or record.fecha_expiracion <= ahora:
                record.dias_restantes = 0
            else:
                record.dias_restantes = BusinessDaysCalculator.count_business_days(
                    ahora, 
                    record.fecha_expiracion
                )
    
    # ==================== MÉTODOS DE CREACIÓN ====================
    @api.model_create_multi
    def create(self, vals_list):
        """
        Override para calcular fecha de expiración automáticamente
        si no se proporciona (5 días hábiles por defecto)
        
        IMPORTANTE: En Odoo 19, el método create siempre recibe una lista de diccionarios (vals_list)
        incluso cuando se crea un solo registro.
        """
        # Iterar sobre cada diccionario en la lista
        for vals in vals_list:
            # Ahora vals SÍ es un diccionario
            if 'fecha_expiracion' not in vals and vals.get('fecha_inicio'):
                fecha_inicio = fields.Datetime.to_datetime(vals['fecha_inicio'])
                vals['fecha_expiracion'] = BusinessDaysCalculator.add_business_days(
                    fecha_inicio, 
                    5
                )
        
        # Llamar al super con vals_list completo
        return super(StockLotHold, self).create(vals_list)
    
    # ==================== ACCIONES ====================
    def action_renovar_hold(self):
        """Renueva la reserva por 5 días hábiles más"""
        self.ensure_one()
        
        if self.estado != 'activo':
            raise UserError('Solo se pueden renovar reservas activas.')
        
        nueva_expiracion = BusinessDaysCalculator.get_expiration_date(days=5)
        self.write({'fecha_expiracion': nueva_expiracion})
        
        mensaje = f'Reserva extendida hasta {nueva_expiracion.strftime("%d/%m/%Y %H:%M")}'
        return NotificationBuilder.build_success('¡Renovado!', mensaje)
    
    def action_cancelar_hold(self):
        """Cancela la reserva activa"""
        self.ensure_one()
        
        if self.estado != 'activo':
            raise UserError('Esta reserva ya no está activa.')
        
        self.write({'estado': 'cancelado'})
    
    # ==================== CRON ====================
    @api.model
    def _cron_expire_holds(self):
        """
        Cron job para expirar automáticamente reservas vencidas
        Se ejecuta cada hora
        """
        ahora = fields.Datetime.now()
        
        holds_expirados = self.search([
            ('estado', '=', 'activo'),
            ('fecha_expiracion', '<=', ahora)
        ])
        
        if holds_expirados:
            holds_expirados.write({'estado': 'expirado'})
            _logger.info("Expiradas %d reservas de lotes", len(holds_expirados))