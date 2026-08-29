# -*- coding: utf-8 -*-
# models/stock_lot_hold.py
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from .utils.business_days import BusinessDaysCalculator
from .utils.notification_builder import NotificationBuilder
from .som_date_format import som_format_date
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
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        readonly=True
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
        string='Embajador',
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
    
    # ==================== CONSTRAINTS (CORREGIDO PARA ODOO 19) ====================
    # _sql_constraints eliminado porque genera error en Odoo 19 al cargar el registro.
    # Se reemplaza por una restricción de Python.
    
    def init(self):
        """Garantía a nivel BASE DE DATOS de 'solo un hold ACTIVO por quant y
        compañía'. El constraint Python no protege contra dos transacciones
        simultáneas (ninguna ve la fila no confirmada de la otra); el índice
        único parcial sí: la segunda revienta al confirmar, sin excepciones."""
        # Sanear duplicados históricos ANTES de crear el índice: se conserva
        # el hold activo más antiguo y los posteriores se marcan expirados.
        self.env.cr.execute("""
            UPDATE stock_lot_hold h
               SET estado = 'expirado'
             WHERE h.estado = 'activo'
               AND EXISTS (
                   SELECT 1 FROM stock_lot_hold h2
                    WHERE h2.quant_id = h.quant_id
                      AND h2.company_id = h.company_id
                      AND h2.estado = 'activo'
                      AND h2.id < h.id
               )
        """)
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS stock_lot_hold_unique_active_idx
                ON stock_lot_hold (quant_id, company_id)
             WHERE estado = 'activo'
        """)

    @api.constrains('quant_id', 'company_id', 'estado')
    def _check_unique_active_hold(self):
        """
        Valida que solo exista una reserva activa por lote y compañía.
        Reemplaza al antiguo _sql_constraints.
        """
        for record in self:
            if record.estado == 'activo':
                domain = [
                    ('quant_id', '=', record.quant_id.id),
                    ('company_id', '=', record.company_id.id),
                    ('estado', '=', 'activo'),
                    ('id', '!=', record.id)  # Excluir el registro actual
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError('Solo puede haber una reserva activa por lote y compañía.')

    # ==================== MÉTODOS COMPUTADOS ====================
    @api.depends('lot_id', 'partner_id', 'company_id')
    def _compute_name(self):
        """Genera referencia del hold"""
        for record in self:
            if record.lot_id and record.partner_id:
                company_suffix = f" ({record.company_id.name})" if record.company_id else ""
                record.name = f"{record.lot_id.name} - {record.partner_id.name}{company_suffix}"
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
        Override para:
        1. Calcular fecha de expiración automáticamente si no se proporciona
        2. Asignar compañía por defecto si no viene en vals
        3. Validar que no exista otro hold activo para el mismo quant en la misma compañía
        """
        for vals in vals_list:
            # Asegurar que tenga company_id
            if 'company_id' not in vals:
                vals['company_id'] = self.env.company.id
            
            # Calcular fecha de expiración si no se proporciona
            if 'fecha_expiracion' not in vals and vals.get('fecha_inicio'):
                fecha_inicio = fields.Datetime.to_datetime(vals['fecha_inicio'])
                # Hora de Monterrey, igual que la orden de reserva.
                vals['fecha_expiracion'] = BusinessDaysCalculator.get_expiration_date(
                    fecha_inicio, 5)
            
            # Validar hold duplicado para la misma compañía
            # Nota: Aunque tenemos el @api.constrains, mantenemos esta validación en create
            # para dar un mensaje de error más amigable antes de intentar guardar.
            if vals.get('quant_id') and vals.get('company_id'):
                # CANDADO TRANSACCIONAL: serializa a dos operaciones que
                # intenten comprometer el MISMO quant al mismo tiempo (galería
                # digital, torre de control, botón de hold, carrito — TODAS
                # crean el hold por aquí). La transacción competidora espera
                # el lock y, al reanudar, la búsqueda de abajo ya ve el hold
                # confirmado por la otra.
                self.env.cr.execute(
                    "SELECT id FROM stock_quant WHERE id = %s FOR UPDATE",
                    [int(vals['quant_id'])],
                )
                hold_existente = self.search([
                    ('quant_id', '=', vals['quant_id']),
                    ('company_id', '=', vals['company_id']),
                    ('estado', '=', 'activo')
                ], limit=1)
                
                if hold_existente:
                    quant = self.env['stock.quant'].browse(vals['quant_id'])
                    company = self.env['res.company'].browse(vals['company_id'])
                    raise UserError(
                        f'Ya existe una reserva activa para el lote {quant.lot_id.name} '
                        f'en la compañía {company.name}. Cliente: {hold_existente.partner_id.name}'
                    )
        
        return super(StockLotHold, self).create(vals_list)
    
    # ==================== ACCIONES ====================
    def action_renovar_hold(self):
        """Renueva la reserva por 5 días hábiles más"""
        self.ensure_one()
        
        if self.estado != 'activo':
            raise UserError('Solo se pueden renovar reservas activas.')
        
        nueva_expiracion = BusinessDaysCalculator.get_expiration_date(days=5)
        self.write({'fecha_expiracion': nueva_expiracion})
        
        mensaje = f'Reserva extendida hasta {som_format_date(nueva_expiracion, with_time=True)}'
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
        Se ejecuta cada hora para TODAS las compañías
        """
        ahora = fields.Datetime.now()

        # TODAS las compañías: el filtro por self.env.company dejaba las
        # reservas de las demás compañías sin expirar NUNCA (inventario
        # bloqueado indefinidamente y ventas perdidas en silencio).
        holds_expirados = self.sudo().search([
            ('estado', '=', 'activo'),
            ('fecha_expiracion', '<=', ahora),
        ])

        # CICLO DE LAS ÓRDENES DE RESERVA: en su PRIMER vencimiento el
        # material se mantiene (sus holds NO se expiran); en el segundo,
        # la orden misma libera todo y deja el detalle en su log.
        HoldOrder = self.env['stock.lot.hold.order'].sudo()

        # T-1 PARA EL CLIENTE: reservas que vencen dentro de las próximas
        # 24 horas — correo con sesgo de escasez (una sola vez; renovar
        # re-arma el aviso).
        from datetime import timedelta
        t1_orders = HoldOrder.search([
            ('state', '=', 'confirmed'),
            ('x_client_expiry_notice_sent', '=', False),
            ('fecha_expiracion', '>', ahora),
            ('fecha_expiracion', '<=', ahora + timedelta(hours=24)),
        ])
        if t1_orders:
            t1_orders._som_notify_client_expiry_tomorrow()

        expired_orders = HoldOrder.search([
            ('state', '=', 'confirmed'),
            ('fecha_expiracion', '<=', ahora),
        ])
        if expired_orders:
            kept_ids = expired_orders._som_process_expiration_cycle()
            # VENDEDOR: actividad en Odoo + correo por cada reserva vencida
            expired_orders._som_notify_seller_expired()
            if kept_ids:
                holds_expirados = holds_expirados.filtered(
                    lambda h: h.id not in kept_ids)

        if holds_expirados:
            holds_expirados.write({'estado': 'expirado'})
            _logger.info(
                "Expiradas %d reservas de lotes en compañía %s", 
                len(holds_expirados),
                self.env.company.name
            )