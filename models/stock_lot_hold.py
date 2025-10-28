# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta

class StockLotHold(models.Model):
    _name = 'stock.lot.hold'
    _description = 'Hold/Reserva Manual de Lotes'
    _order = 'create_date desc'
    _rec_name = 'lot_id'

    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    quant_id = fields.Many2one(
        'stock.quant',
        string='Quant',
        required=True,
        ondelete='cascade',
        index=True,
        help='Referencia al quant específico que se está reservando'
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Reservado Para',
        required=True,
        help='Cliente o contacto para quien se reserva el lote'
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Reservado Por',
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
        help='Usuario que creó la reserva'
    )
    
    fecha_inicio = fields.Datetime(
        string='Fecha de Reserva',
        required=True,
        default=fields.Datetime.now,
        readonly=True,
        help='Fecha y hora en que se creó la reserva'
    )
    
    fecha_expiracion = fields.Datetime(
        string='Fecha de Expiración',
        compute='_compute_fecha_expiracion',
        store=True,
        help='Fecha en que expira la reserva (10 días desde inicio)'
    )
    
    estado = fields.Selection([
        ('activo', 'Activo'),
        ('expirado', 'Expirado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='activo', required=True, index=True)
    
    notas = fields.Text(
        string='Notas',
        help='Notas adicionales sobre esta reserva'
    )
    
    dias_restantes = fields.Integer(
        string='Días Restantes',
        compute='_compute_dias_restantes',
        store=False,  # CAMBIADO: No se guarda en BD
        help='Días restantes hasta la expiración'
    )
    
    esta_expirado = fields.Boolean(
        string='Expirado',
        compute='_compute_esta_expirado',  # CAMBIADO: Método separado
        store=True,
        help='Indica si la reserva ya expiró'
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

    @api.depends('fecha_inicio')
    def _compute_fecha_expiracion(self):
        """Calcular fecha de expiración (10 días desde inicio)"""
        for record in self:
            if record.fecha_inicio:
                record.fecha_expiracion = record.fecha_inicio + timedelta(days=10)
            else:
                record.fecha_expiracion = fields.Datetime.now() + timedelta(days=10)

    @api.depends('fecha_expiracion')
    def _compute_dias_restantes(self):
        """Calcular días restantes hasta expiración"""
        now = fields.Datetime.now()
        for record in self:
            if record.fecha_expiracion:
                delta = record.fecha_expiracion - now
                record.dias_restantes = delta.days
            else:
                record.dias_restantes = 0

    @api.depends('fecha_expiracion', 'estado')
    def _compute_esta_expirado(self):
        """Marcar si la reserva está expirada"""
        now = fields.Datetime.now()
        for record in self:
            if record.fecha_expiracion and record.estado == 'activo':
                delta = record.fecha_expiracion - now
                record.esta_expirado = delta.days < 0
            else:
                record.esta_expirado = False

    @api.model
    def _cron_expire_holds(self):
        """Cron job para expirar reservas automáticamente"""
        now = fields.Datetime.now()
        holds_expirados = self.search([
            ('estado', '=', 'activo'),
            ('fecha_expiracion', '<=', now)
        ])
        
        if holds_expirados:
            holds_expirados.write({'estado': 'expirado'})
            # Forzar recálculo de estados en los quants relacionados
            quants = holds_expirados.mapped('quant_id')
            quants._compute_estado_hold()
            
        return True

    def action_cancelar_hold(self):
        """Cancelar manualmente una reserva"""
        self.ensure_one()
        self.write({'estado': 'cancelado'})
        # Forzar recálculo del estado del quant
        self.quant_id._compute_estado_hold()
        return True

    def action_renovar_hold(self):
        """Renovar la reserva por 10 días más"""
        self.ensure_one()
        if self.estado == 'activo':
            self.write({
                'fecha_inicio': fields.Datetime.now(),
                'estado': 'activo'
            })
            # Forzar recálculo de fecha de expiración
            self._compute_fecha_expiracion()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '¡Éxito!',
                    'message': f'Reserva renovada hasta {self.fecha_expiracion.strftime("%d/%m/%Y")}',
                    'type': 'success',
                    'sticky': False,
                }
            }
        return True

    @api.model_create_multi
    def create(self, vals_list):
        """Al crear, verificar que no haya otro hold activo en el mismo quant"""
        for vals in vals_list:
            if 'quant_id' in vals:
                hold_existente = self.search([
                    ('quant_id', '=', vals['quant_id']),
                    ('estado', '=', 'activo')
                ], limit=1)
                if hold_existente:
                    raise models.ValidationError(
                        f"Este lote ya tiene una reserva activa para {hold_existente.partner_id.name} "
                        f"que expira el {hold_existente.fecha_expiracion.strftime('%d/%m/%Y')}"
                    )
        return super().create(vals_list)

    def unlink(self):
        """Al eliminar, forzar recálculo de estados"""
        quants = self.mapped('quant_id')
        result = super().unlink()
        quants._compute_estado_hold()
        return result

    def write(self, vals):
        """Al modificar estado, forzar recálculo"""
        result = super().write(vals)
        if 'estado' in vals:
            self.mapped('quant_id')._compute_estado_hold()
        return result