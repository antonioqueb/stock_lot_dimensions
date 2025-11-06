# ./models/stock_lot_hold.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class StockLotHold(models.Model):
    _name = 'stock.lot.hold'
    _description = 'Reservas Manuales de Lotes'
    _order = 'fecha_inicio desc'
    
    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    
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
    
    estado = fields.Selection([
        ('activo', 'Activo'),
        ('expirado', 'Expirado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='activo', required=True, index=True)
    
    notas = fields.Text(string='Notas')
    
    dias_restantes = fields.Integer(
        string='Días Hábiles Restantes',
        compute='_compute_dias_restantes'
    )

    @api.depends('lot_id', 'partner_id')
    def _compute_name(self):
        for record in self:
            if record.lot_id and record.partner_id:
                record.name = f"{record.lot_id.name} - {record.partner_id.name}"
            else:
                record.name = "Hold"

    @api.depends('fecha_expiracion', 'estado')
    def _compute_dias_restantes(self):
        ahora = fields.Datetime.now()
        for record in self:
            if record.estado != 'activo':
                record.dias_restantes = 0
            elif record.fecha_expiracion <= ahora:
                record.dias_restantes = 0
            else:
                record.dias_restantes = record._calcular_dias_habiles_entre(ahora, record.fecha_expiracion)

    def _calcular_dias_habiles_entre(self, fecha_inicio, fecha_fin):
        dias = 0
        fecha_actual = fecha_inicio
        while fecha_actual.date() < fecha_fin.date():
            if fecha_actual.weekday() < 5:
                dias += 1
            fecha_actual += timedelta(days=1)
        return dias

    def _calcular_dias_habiles(self, fecha_inicio, dias_habiles):
        fecha_actual = fecha_inicio
        dias_agregados = 0
        while dias_agregados < dias_habiles:
            fecha_actual += timedelta(days=1)
            if fecha_actual.weekday() < 5:
                dias_agregados += 1
        return fecha_actual

    @api.model
    def create(self, vals):
        if 'fecha_expiracion' not in vals and vals.get('fecha_inicio'):
            fecha_inicio = fields.Datetime.to_datetime(vals['fecha_inicio'])
            vals['fecha_expiracion'] = self._calcular_dias_habiles(fecha_inicio, 5)
        return super().create(vals)

    def action_renovar_hold(self):
        self.ensure_one()
        if self.estado != 'activo':
            raise UserError('Solo se pueden renovar reservas activas.')
        
        nueva_expiracion = self._calcular_dias_habiles(fields.Datetime.now(), 5)
        self.write({'fecha_expiracion': nueva_expiracion})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '¡Renovado!',
                'message': f'Reserva extendida hasta {nueva_expiracion.strftime("%d/%m/%Y %H:%M")}',
                'type': 'success',
            }
        }

    def action_cancelar_hold(self):
        self.ensure_one()
        if self.estado != 'activo':
            raise UserError('Esta reserva ya no está activa.')
        
        self.write({'estado': 'cancelado'})

    @api.model
    def _cron_expire_holds(self):
        ahora = fields.Datetime.now()
        holds_expirados = self.search([
            ('estado', '=', 'activo'),
            ('fecha_expiracion', '<=', ahora)
        ])
        
        if holds_expirados:
            holds_expirados.write({'estado': 'expirado'})
            _logger.info(f"Se expiraron {len(holds_expirados)} reservas de lotes")