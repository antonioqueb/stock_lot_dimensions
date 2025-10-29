# -*- coding: utf-8 -*-
from odoo import models, fields, api
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
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Reservar Para',
        required=True,
        help='Cliente o contacto para quien se reserva el lote'
    )
    
    fecha_expiracion = fields.Datetime(
        string='Expira el',
        compute='_compute_fecha_expiracion',
        readonly=True,
        help='Fecha de expiración (10 días desde hoy)'
    )
    
    notas = fields.Text(
        string='Notas',
        placeholder='Notas adicionales sobre esta reserva...'
    )
    
    # Campos informativos del lote
    x_grosor = fields.Float(related='lot_id.x_grosor', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', readonly=True)
    x_formato = fields.Selection(related='lot_id.x_formato', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', readonly=True)
    x_atado = fields.Char(related='lot_id.x_atado', readonly=True)

    @api.depends('create_date')
    def _compute_fecha_expiracion(self):
        """Calcular fecha de expiración (10 días)"""
        for record in self:
            record.fecha_expiracion = fields.Datetime.now() + timedelta(days=10)

    def action_crear_hold(self):
        """Crear el hold y cerrar el wizard"""
        self.ensure_one()
        
        # Verificar que no haya hold activo
        hold_existente = self.env['stock.lot.hold'].search([
            ('quant_id', '=', self.quant_id.id),
            ('estado', '=', 'activo')
        ], limit=1)
        
        if hold_existente:
            raise models.UserError(
                f'Este lote ya tiene una reserva activa para {hold_existente.partner_id.name} '
                f'que expira el {hold_existente.fecha_expiracion.strftime("%d/%m/%Y")}'
            )
        
        # Crear el hold
        hold = self.env['stock.lot.hold'].create({
            'lot_id': self.lot_id.id,
            'quant_id': self.quant_id.id,
            'partner_id': self.partner_id.id,
            'notas': self.notas,
        })
        
        # Retornar notificación de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '¡Reserva Creada!',
                'message': f'Lote {self.lot_id.name} reservado para {self.partner_id.name} hasta el {hold.fecha_expiracion.strftime("%d/%m/%Y %H:%M")}',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }