## ./__init__.py
```py
# -*- coding: utf-8 -*-
from . import models
from . import wizard
```

## ./__manifest__.py
```py
# -*- coding: utf-8 -*-
{
    'name': 'Atributos Adicionales para Lotes',
    'version': '19.0.2.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Captura dimensiones, fotografías y gestión de reservas manuales (hold) en lotes',
    'description': """
        Módulo que permite:
        - Capturar dimensiones (grosor, alto, ancho) y fotografías al recepcionar productos
        - Almacenar esta información en los lotes
        - Visualizar atributos en reportes de inventario
        - Mostrar estados de reserva y detalles de placas
        - Gestionar reservas manuales (holds) independientes de órdenes de venta
        - Expiración automática de reservas a los 5 días hábiles (lunes a viernes)
    """,
    'author': 'Alphaqueb Consulting',
    'website': 'https://alphaqueb.com',
    'depends': ['stock', 'sale', 'web', 'project'],
    'data': [
        'security/stock_lot_hold_security.xml',
        'security/ir.model.access.csv',
        'data/stock_lot_hold_cron.xml',
        'data/stock_lot_hold_order_sequence.xml',
        'reports/stock_lot_hold_order_report.xml',  # ← DEBE IR ANTES DE LAS VISTAS
        'views/stock_lot_views.xml',
        'views/stock_lot_group_views.xml',
        'views/stock_move_views.xml',
        'views/stock_quant_views.xml',
        'views/stock_lot_image_wizard_views.xml',
        'views/stock_lot_hold_views.xml',
        'views/stock_lot_hold_order_views.xml',  # ← AHORA PUEDE USAR EL REPORTE
        'views/stock_lot_hold_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/project_project_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_lot_dimensions/static/src/js/image_gallery_widget.js',
            'stock_lot_dimensions/static/src/js/image_preview_widget.js',
            'stock_lot_dimensions/static/src/js/status_icons_widget.js',
            'stock_lot_dimensions/static/src/css/image_gallery.css',
            'stock_lot_dimensions/static/src/css/image_gallery_view.css',
            'stock_lot_dimensions/static/src/xml/image_gallery.xml',
            'stock_lot_dimensions/static/src/xml/image_preview_widget.xml',
            'stock_lot_dimensions/static/src/xml/status_icons_widget.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}```

## ./data/stock_lot_hold_cron.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Cron Job para expirar reservas automáticamente -->
    <!-- El cron debe respetar compañías -->
    <record id="ir_cron_expire_lot_holds" model="ir.cron">
        <field name="name">Expirar Reservas de Lotes</field>
        <field name="model_id" ref="model_stock_lot_hold"/>
        <field name="state">code</field>
        <field name="code">
companies = env['res.company'].search([])
for company in companies:
    model.with_company(company)._cron_expire_holds()
        </field>
        <field name="interval_number">1</field>
        <field name="interval_type">hours</field>
        <field name="active">True</field>
        <field name="priority">10</field>
    </record>
</odoo>```

## ./data/stock_lot_hold_order_sequence.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">
        <record id="seq_stock_lot_hold_order" model="ir.sequence">
            <field name="name">Orden de Reserva de Lotes</field>
            <field name="code">stock.lot.hold.order</field>
            <field name="prefix">RES/</field>
            <field name="padding">5</field>
            <field name="company_id" eval="False"/>
        </record>
    </data>
</odoo>```

## ./models/__init__.py
```py
# -*- coding: utf-8 -*-
from . import utils
from . import stock_lot
from . import stock_lot_image
from . import stock_move_line
from . import stock_picking
from . import stock_lot_hold 
from . import stock_quant
from . import sale_order
from . import stock_lot_group
from . import project_project
from . import res_partner
from . import stock_lot_hold_order```

## ./models/project_project.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields

class ProjectProject(models.Model):
    _inherit = 'project.project'
    
    x_es_proyecto_marmol = fields.Boolean(
        string='Es Proyecto de Mármol',
        default=False,
        help='Indica si este proyecto está relacionado con reservas de lotes de mármol'
    )```

## ./models/res_partner.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    x_es_arquitecto = fields.Boolean(
        string='Es Arquitecto',
        default=False,
        help='Indica si este contacto es un arquitecto'
    )```

## ./models/sale_order.py
```py
# -*- coding: utf-8 -*-
# models/sale_order.py
from odoo import models, api
from .utils.picking_cleaner import PickingLotCleaner
import logging
_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def action_confirm(self):
        """
        Override para:
        1. Filtrar holds por cliente (contexto allowed_partner_id)
        2. Limpiar lotes automáticos post-confirmación
        """
        _logger.info("Confirmando órdenes: %s", self.mapped('name'))
        
        # 🔑 CRÍTICO: Ejecutar super() en el recordset completo PRIMERO
        # Construir contexto agregado con todos los clientes
        all_partner_ids = self.mapped('partner_id.id')
        context = dict(self.env.context)
        
        if all_partner_ids:
            # Si hay un solo cliente, usar allowed_partner_id
            if len(all_partner_ids) == 1:
                context['allowed_partner_id'] = all_partner_ids[0]
            # Si hay múltiples clientes, usar lista (para filtrado más complejo)
            else:
                context['allowed_partner_ids'] = all_partner_ids
        
        # Ejecutar confirmación con contexto
        res = super(SaleOrder, self.with_context(**context)).action_confirm()
        
        # Limpiar lotes automáticos DESPUÉS de confirmar
        self._clear_auto_assigned_lots()
        
        return res
    
    def _clear_auto_assigned_lots(self):
        """Limpia lotes automáticos usando utilidad centralizada"""
        cleaner = PickingLotCleaner(self.env)
        for order in self:
            if order.picking_ids:
                cleaner.clear_pickings_lots(order.picking_ids)```

## ./models/stock_lot_group.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields

class StockLotGroup(models.Model):
    _name = 'stock.lot.group'
    _description = 'Grupos/Etiquetas de Lotes'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre del grupo/etiqueta'
    )
    
    color = fields.Integer(
        string='Color',
        help='Color de la etiqueta en la interfaz'
    )
    
    active = fields.Boolean(
        string='Activo',
        default=True
    )```

## ./models/stock_lot_hold_order.py
```py
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
        default=10
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
                }```

## ./models/stock_lot_hold.py
```py
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
    
    # ==================== CONSTRAINTS ====================
    _sql_constraints = [
        ('unique_active_hold_per_company', 
         'UNIQUE(quant_id, company_id, estado)',
         'Solo puede haber una reserva activa por lote y compañía.')
    ]
    
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
                vals['fecha_expiracion'] = BusinessDaysCalculator.add_business_days(
                    fecha_inicio, 
                    5
                )
            
            # Validar hold duplicado para la misma compañía
            if vals.get('quant_id') and vals.get('company_id'):
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
        Se ejecuta cada hora para TODAS las compañías
        """
        ahora = fields.Datetime.now()
        
        # Buscar holds expirados de la compañía actual
        holds_expirados = self.search([
            ('estado', '=', 'activo'),
            ('fecha_expiracion', '<=', ahora),
            ('company_id', '=', self.env.company.id)
        ])
        
        if holds_expirados:
            holds_expirados.write({'estado': 'expirado'})
            _logger.info(
                "Expiradas %d reservas de lotes en compañía %s", 
                len(holds_expirados),
                self.env.company.name
            )```

## ./models/stock_lot_image.py
```py
# -*- coding: utf-8 -*-
# models/stock_lot_image.py
from odoo import models, fields, api
from .utils.image_processor import ImageProcessor
from .utils.metadata_fields import MetadataFields


class StockLotImage(models.Model):
    _name = 'stock.lot.image'
    _description = 'Fotografías de Lotes'
    _order = ImageProcessor.get_default_order()
    
    # ==================== CAMPOS METADATA ====================
    name = MetadataFields.get_name_field(default_name='Fotografía')
    sequence = MetadataFields.get_sequence_field(default=10)
    notas = MetadataFields.get_notes_field()
    fecha_captura = MetadataFields.get_capture_date_field()
    
    # ==================== CAMPOS DE RELACIÓN ====================
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    # ==================== CAMPOS DE IMAGEN ====================
    image = fields.Binary(
        string='Imagen',
        required=True,
        attachment=True
    )
    
    image_small = fields.Binary(
        string='Miniatura',
        compute='_compute_image_small',
        store=True
    )
    
    # ==================== MÉTODOS COMPUTADOS ====================
    @api.depends('image')
    def _compute_image_small(self):
        """Generar miniatura de la imagen"""
        ImageProcessor.compute_thumbnail(self)```

## ./models/stock_lot.py
```py
# -*- coding: utf-8 -*-
# models/stock_lot.py
from odoo import models, fields, api
from .utils.dimension_fields import LotDimensionFields
from .utils.photo_helpers import PhotoHelper


class StockLot(models.Model):
    _inherit = 'stock.lot'
    
    # ==================== CAMPOS DE DIMENSIONES ====================
    x_grosor = LotDimensionFields.get_dimension_fields()['x_grosor']
    x_alto = LotDimensionFields.get_dimension_fields()['x_alto']
    x_ancho = LotDimensionFields.get_dimension_fields()['x_ancho']
    
    # ==================== CAMPOS DE CLASIFICACIÓN ====================
    x_tipo = LotDimensionFields.get_classification_fields()['x_tipo']
    x_bloque = LotDimensionFields.get_classification_fields()['x_bloque']
    x_atado = LotDimensionFields.get_classification_fields()['x_atado']
    x_grupo = LotDimensionFields.get_classification_fields()['x_grupo']
    
    # ==================== CAMPOS LOGÍSTICOS ====================
    x_pedimento = LotDimensionFields.get_logistics_fields()['x_pedimento']
    x_contenedor = LotDimensionFields.get_logistics_fields()['x_contenedor']
    x_referencia_proveedor = LotDimensionFields.get_logistics_fields()['x_referencia_proveedor']
    
    # ==================== CAMPOS DE FOTOGRAFÍAS ====================
    x_fotografia_ids = PhotoHelper.get_photo_fields()['x_fotografia_ids']
    x_fotografia_principal = PhotoHelper.get_photo_fields()['x_fotografia_principal']
    x_tiene_fotografias = PhotoHelper.get_photo_fields()['x_tiene_fotografias']
    x_cantidad_fotos = PhotoHelper.get_photo_fields()['x_cantidad_fotos']
    
    # ==================== CAMPO ADICIONAL ====================
    x_detalles_placa = fields.Text(
        string='Detalles de la Placa',
        help='Detalles especiales: rota, barreno, release, etc.'
    )
    
    # ==================== MÉTODOS COMPUTADOS ====================
    @api.depends('x_fotografia_ids')
    def _compute_fotografia_principal(self):
        """Obtener la primera fotografía como principal"""
        PhotoHelper.compute_main_photo(self)
    
    @api.depends('x_fotografia_ids')
    def _compute_tiene_fotografias(self):
        """Verificar si el lote tiene fotografías"""
        PhotoHelper.compute_has_photos(self)
    
    @api.depends('x_fotografia_ids')
    def _compute_cantidad_fotos(self):
        """Contar número de fotografías"""
        PhotoHelper.compute_photo_count(self)
    
    # ==================== ACCIONES ====================
    def action_view_images(self):
        """Abrir vista de galería de imágenes del lote"""
        self.ensure_one()
        return PhotoHelper.build_photo_gallery_action(self.id, self.name)```

## ./models/stock_move_line.py
```py
# -*- coding: utf-8 -*-
# models/stock_move_line.py
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from .utils.dimension_fields import LotDimensionFields
from .utils.hold_validator import HoldValidator
from .utils.lot_dimension_sync import LotDimensionSync
from .utils.notification_builder import NotificationBuilder
from .utils.photo_helpers import PhotoHelper
import logging

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    
    # ==================== CAMPOS TEMPORALES DE DIMENSIONES ====================
    x_grosor_temp = fields.Float(
        string='Grosor (cm)',
        digits=(10, 2),
        help='Grosor del producto en centímetros (se guardará en el lote)'
    )
    
    x_alto_temp = fields.Float(
        string='Alto (m)',
        digits=(10, 4),
        help='Alto del producto en metros (se guardará en el lote)'
    )
    
    x_ancho_temp = fields.Float(
        string='Ancho (m)',
        digits=(10, 4),
        help='Ancho del producto en metros (se guardará en el lote)'
    )
    
    x_tipo_temp = fields.Selection(
        [('placa', 'Placa'), ('formato', 'Formato')],
        string='Tipo',
        help='Tipo de producto (se guardará en el lote)'
    )
    
    x_bloque_temp = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen (se guardará en el lote)'
    )
    
    x_atado_temp = fields.Char(
        string='Atado',
        help='Identificación del atado (se guardará en el lote)'
    )
    
    x_grupo_temp = fields.Many2many(
        'stock.lot.group',
        string='Grupo',
        help='Grupos del lote (se guardarán en el lote)'
    )
    
    x_pedimento_temp = fields.Char(
        string='Pedimento',
        help='Número de pedimento (se guardará en el lote)'
    )
    
    x_contenedor_temp = fields.Char(
        string='Contenedor',
        help='Número de contenedor (se guardará en el lote)'
    )
    
    x_referencia_proveedor_temp = fields.Char(
        string='Referencia Proveedor',
        help='Referencia del proveedor (se guardará en el lote)'
    )
    
    # ==================== CAMPOS COMPUTADOS ====================
    x_is_incoming = fields.Boolean(
        string='Es Recepción',
        compute='_compute_is_incoming',
        store=False
    )
    
    # ==================== CAMPOS RELATED DEL LOTE ====================
    x_grosor_lote = fields.Float(
        related='lot_id.x_grosor',
        string='Grosor Lote (cm)',
        readonly=True,
        store=False
    )
    
    x_alto_lote = fields.Float(
        related='lot_id.x_alto',
        string='Alto Lote (m)',
        readonly=True,
        store=False
    )
    
    x_ancho_lote = fields.Float(
        related='lot_id.x_ancho',
        string='Ancho Lote (m)',
        readonly=True,
        store=False
    )
    
    x_tipo_lote = fields.Selection(
        related='lot_id.x_tipo',
        string='Tipo Lote',
        readonly=True,
        store=False
    )
    
    x_bloque_lote = fields.Char(
        related='lot_id.x_bloque',
        string='Bloque Lote',
        readonly=True,
        store=False
    )
    
    x_atado_lote = fields.Char(
        related='lot_id.x_atado',
        string='Atado Lote',
        readonly=True,
        store=False
    )
    
    x_grupo_lote = fields.Many2many(
        related='lot_id.x_grupo',
        string='Grupo Lote',
        readonly=True,
        store=False
    )
    
    x_pedimento_lote = fields.Char(
        related='lot_id.x_pedimento',
        string='Pedimento Lote',
        readonly=True,
        store=False
    )
    
    x_contenedor_lote = fields.Char(
        related='lot_id.x_contenedor',
        string='Contenedor Lote',
        readonly=True,
        store=False
    )
    
    x_referencia_proveedor_lote = fields.Char(
        related='lot_id.x_referencia_proveedor',
        string='Ref. Proveedor Lote',
        readonly=True,
        store=False
    )
    
    x_fotografia_principal_lote = fields.Binary(
        related='lot_id.x_fotografia_principal',
        string='Foto Lote',
        readonly=True,
        store=False
    )
    
    x_cantidad_fotos_lote = fields.Integer(
        related='lot_id.x_cantidad_fotos',
        string='# Fotos Lote',
        readonly=True,
        store=False
    )
    
    # ==================== MÉTODOS COMPUTADOS ====================
    @api.depends('picking_id', 'picking_id.picking_type_code')
    def _compute_is_incoming(self):
        """Determinar si la línea pertenece a una recepción"""
        for line in self:
            line.x_is_incoming = (
                line.picking_id and 
                line.picking_id.picking_type_code == 'incoming'
            )
    
    # ==================== VALIDACIONES DE HOLDS ====================
    @api.constrains('lot_id', 'picking_id', 'state')
    def _check_lot_hold(self):
        """Validación de holds al asignar/confirmar lotes con soporte multi-compañía"""
        # Bypass si ya se validó
        if self._context.get('skip_hold_validation'):
            return
        
        validator = HoldValidator(self.env)
        
        for line in self:
            # Solo validar pickings de salida con lote asignado
            if not line.lot_id or not line.picking_id:
                continue
            
            if line.picking_id.picking_type_code != 'outgoing':
                continue
            
            # Obtener cliente
            partner = validator.get_customer_from_picking(line)
            if not partner:
                continue
            
            # Obtener compañía del picking
            company_id = line.picking_id.company_id.id if line.picking_id.company_id else self.env.company.id
            
            # Validar hold considerando compañía
            try:
                validator.validate_lot_assignment(
                    line.lot_id.id,
                    line.location_id.id,
                    partner.id,
                    company_id
                )
            except ValidationError:
                raise
    
    # ==================== ONCHANGE - FILTRADO DE LOTES ====================
    @api.onchange('product_id', 'location_id', 'picking_id')
    def _onchange_product_location_filter_lots(self):
        """Filtrar lotes disponibles según holds del cliente y compañía"""
        if not self.product_id or not self.picking_id:
            return {}
        
        # Solo aplicar en pickings de salida
        if self.picking_id.picking_type_code != 'outgoing':
            return {}
        
        validator = HoldValidator(self.env)
        partner = validator.get_customer_from_picking(self)
        
        if not partner or not self.location_id:
            return {'domain': {'lot_id': [('id', '=', False)]}}
        
        # Obtener compañía del picking
        company_id = self.picking_id.company_id.id if self.picking_id.company_id else self.env.company.id
        
        # Obtener lotes disponibles considerando compañía
        available_lots = validator.get_available_lots(
            self.product_id.id,
            self.location_id.id,
            partner.id,
            company_id
        )
        
        if available_lots:
            return {
                'domain': {
                    'lot_id': [
                        ('id', 'in', available_lots),
                        ('product_id', '=', self.product_id.id)
                    ]
                }
            }
        else:
            return {'domain': {'lot_id': [('id', '=', False)]}}
    
    # ==================== ONCHANGE - DIMENSIONES ====================
    @api.onchange('lot_id')
    def _onchange_lot_id_dimensions(self):
        """Cargar dimensiones del lote y calcular cantidad"""
        if not self.lot_id:
            return
        
        # Cargar dimensiones
        LotDimensionSync.load_dimensions_from_lot(self)
        
        if not self.picking_id:
            return
        
        # Calcular cantidad según tipo de picking
        if self.picking_id.picking_type_code == 'incoming':
            # Recepción: Calcular por dimensiones
            self.qty_done = LotDimensionSync.calculate_area(
                self.lot_id.x_alto,
                self.lot_id.x_ancho
            )
        
        elif self.picking_id.picking_type_code == 'outgoing':
            # Entrega: Usar cantidad disponible
            move_qty = self.move_id.product_uom_qty if self.move_id else None
            
            self.qty_done = LotDimensionSync.get_available_quantity(
                self.env,
                self.lot_id.id,
                self.location_id.id,
                self.product_id.id,
                move_qty
            )
    
    @api.onchange('x_alto_temp', 'x_ancho_temp')
    def _onchange_calcular_cantidad(self):
        """Calcular qty_done automáticamente cuando se ingresan dimensiones"""
        if not self.picking_id or self.picking_id.picking_type_code != 'incoming':
            return
        
        self.qty_done = LotDimensionSync.calculate_area(
            self.x_alto_temp,
            self.x_ancho_temp
        )
    
    # ==================== WRITE ====================
    def write(self, vals):
        """Guardar dimensiones en el lote y validar holds con soporte multi-compañía"""
        # Validar hold si se está cambiando el lote
        if 'lot_id' in vals and vals['lot_id']:
            self._validate_lot_hold_on_write(vals['lot_id'])
        
        # Ejecutar write original
        result = super().write(vals)
        
        # Sincronizar dimensiones al lote
        self._sync_dimensions_to_lot(vals)
        
        # Calcular cantidad si se modificaron dimensiones
        self._update_qty_done_if_needed(vals)
        
        return result
    
    def _validate_lot_hold_on_write(self, new_lot_id):
        """Valida hold al cambiar lote en write con soporte multi-compañía"""
        validator = HoldValidator(self.env)
        
        for line in self:
            # Solo validar pickings de salida
            if not line.picking_id or line.picking_id.picking_type_code != 'outgoing':
                continue
            
            partner = validator.get_customer_from_picking(line)
            if not partner:
                continue
            
            # Obtener compañía del picking
            company_id = line.picking_id.company_id.id if line.picking_id.company_id else self.env.company.id
            
            try:
                validator.validate_lot_assignment(
                    new_lot_id,
                    line.location_id.id,
                    partner.id,
                    company_id
                )
            except ValidationError:
                raise
    
    def _sync_dimensions_to_lot(self, vals):
        """Sincroniza dimensiones temporales al lote"""
        dimension_fields = list(LotDimensionSync.DIMENSION_MAPPING.keys())
        has_dimensions = any(field in vals for field in dimension_fields)
        
        if 'lot_id' not in vals and not has_dimensions:
            return
        
        for line in self:
            # Solo en recepciones
            if not line.lot_id or not line.picking_id:
                continue
            
            if line.picking_id.picking_type_code != 'incoming':
                continue
            
            lot_vals = LotDimensionSync.sync_dimensions_to_lot(line)
            
            if lot_vals:
                line.lot_id.write(lot_vals)
    
    def _update_qty_done_if_needed(self, vals):
        """Actualiza qty_done si cambiaron dimensiones"""
        if ('x_alto_temp' not in vals and 'x_ancho_temp' not in vals) or 'qty_done' in vals:
            return
        
        for line in self:
            if not line.picking_id or line.picking_id.picking_type_code != 'incoming':
                continue
            
            qty_done = LotDimensionSync.calculate_area(
                line.x_alto_temp,
                line.x_ancho_temp
            )
            
            if qty_done > 0:
                super(StockMoveLine, line).write({'qty_done': qty_done})
    
    # ==================== CREATE ====================
    @api.model_create_multi
    def create(self, vals_list):
        """Guardar dimensiones en el lote y calcular cantidad al crear"""
        # Pre-calcular qty_done en recepciones
        for vals in vals_list:
            picking_id = vals.get('picking_id')
            if picking_id:
                picking = self.env['stock.picking'].browse(picking_id)
                if picking.picking_type_code == 'incoming':
                    qty_done = LotDimensionSync.calculate_area(
                        vals.get('x_alto_temp'),
                        vals.get('x_ancho_temp')
                    )
                    if qty_done > 0:
                        vals['qty_done'] = qty_done
        
        # Crear registros
        lines = super().create(vals_list)
        
        # Sincronizar dimensiones al lote
        for line in lines:
            if not line.lot_id or not line.picking_id:
                continue
            
            if line.picking_id.picking_type_code != 'incoming':
                continue
            
            lot_vals = LotDimensionSync.sync_dimensions_to_lot(line)
            if lot_vals:
                line.lot_id.write(lot_vals)
        
        return lines
    
    # ==================== ACCIONES ====================
    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote"""
        self.ensure_one()
        
        if not self.lot_id:
            return NotificationBuilder.build_warning(
                'Advertencia',
                'Debe seleccionar un lote primero'
            )
        
        return {
            'name': 'Agregar Fotografía',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lot_id': self.lot_id.id,
                'default_name': f'Foto - {self.lot_id.name}',
            }
        }
    
    def action_view_lot_photos(self):
        """Ver fotografías del lote"""
        self.ensure_one()
        
        if not self.lot_id:
            raise UserError('Debe seleccionar un lote primero.')
        
        return PhotoHelper.build_photo_gallery_action(
            self.lot_id.id,
            self.lot_id.name
        )


class StockLot(models.Model):
    _inherit = 'stock.lot'
    
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Filtrado adicional de lotes en búsqueda considerando holds y multi-compañía"""
        move_line_id = self.env.context.get('move_line_id')
        
        if move_line_id:
            move_line = self.env['stock.move.line'].browse(move_line_id)
            
            # Solo filtrar en pickings de salida
            if move_line.picking_id and move_line.picking_id.picking_type_code == 'outgoing':
                validator = HoldValidator(self.env)
                partner = validator.get_customer_from_picking(move_line)
                
                if partner:
                    # Obtener compañía del picking
                    company_id = (
                        move_line.picking_id.company_id.id 
                        if move_line.picking_id.company_id 
                        else self.env.company.id
                    )
                    
                    # Obtener lotes disponibles considerando compañía
                    available_lots = validator.get_available_lots(
                        move_line.product_id.id,
                        move_line.location_id.id,
                        partner.id,
                        company_id
                    )
                    
                    # Actualizar args
                    if args is None:
                        args = []
                    args = list(args) + [('id', 'in', available_lots)]
        
        return super(StockLot, self).name_search(
            name=name,
            args=args,
            operator=operator,
            limit=limit
        )```

## ./models/stock_picking.py
```py
# -*- coding: utf-8 -*-
# models/stock_picking.py
from odoo import models, api
from odoo.exceptions import UserError
from .utils.picking_cleaner import PickingLotCleaner
from .utils.hold_validator import HoldValidator
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    def action_assign(self):
        """
        Override para filtrar quants con hold al reservar
        Añade el contexto de cliente permitido para filtrado FIFO/LIFO
        Considera multi-compañía
        """
        for picking in self:
            if self._should_filter_by_hold(picking):
                context = self._build_hold_context(picking)
                self = self.with_context(**context)
        
        return super(StockPicking, self).action_assign()
    
    def _action_assign(self):
        """
        Override para limpiar lotes automáticos después de la asignación
        Solo limpia lotes de pickings que vienen de órdenes de venta
        """
        # Ejecutar asignación normal
        result = super(StockPicking, self)._action_assign()
        
        # Limpiar lotes automáticos de pickings de sale orders
        self._clear_auto_assigned_lots_from_sales()
        
        return result
    
    def button_validate(self):
        """
        Validar holds antes de validar el picking
        Verifica que los lotes asignados no tengan holds de otros clientes
        Considera multi-compañía
        """
        self._validate_holds_before_transfer()
        
        return super(StockPicking, self).button_validate()
    
    # ==================== MÉTODOS AUXILIARES ====================
    
    def _should_filter_by_hold(self, picking):
        """
        Determina si se debe filtrar por holds
        
        Args:
            picking: stock.picking record
            
        Returns:
            bool: True si se debe filtrar
        """
        return (
            picking.picking_type_code == 'outgoing' and 
            picking.partner_id
        )
    
    def _build_hold_context(self, picking):
        """
        Construye contexto con información de cliente y empresa
        
        Args:
            picking: stock.picking record
            
        Returns:
            dict: Contexto actualizado con allowed_partner_id y company_id
        """
        company_id = picking.company_id.id if picking.company_id else self.env.company.id
        
        context = {
            'allowed_partner_id': picking.partner_id.id,
            'company_id': company_id
        }
        
        _logger.debug(
            "Contexto de holds para picking %s: Cliente=%s, Compañía=%s",
            picking.name,
            picking.partner_id.name,
            company_id
        )
        
        return context
    
    def _clear_auto_assigned_lots_from_sales(self):
        """Limpia lotes automáticos solo de pickings que vienen de sale orders"""
        cleaner = PickingLotCleaner(self.env)
        
        # Filtrar solo pickings de sale orders
        sale_pickings = self.filtered(lambda p: p.sale_id)
        
        if sale_pickings:
            _logger.info(
                "Limpiando lotes automáticos de %d pickings de sale orders: %s",
                len(sale_pickings),
                sale_pickings.mapped('name')
            )
            cleaner.clear_pickings_lots(sale_pickings)
    
    def _validate_holds_before_transfer(self):
        """
        Valida que todos los lotes asignados no tengan holds de otros clientes
        Considera multi-compañía: solo valida holds de la misma compañía
        
        Raises:
            UserError: Si algún lote está reservado para otro cliente en la misma compañía
        """
        validator = HoldValidator(self.env)
        
        for picking in self:
            # Solo validar pickings de salida
            if picking.picking_type_code != 'outgoing':
                continue
            
            company_id = picking.company_id.id if picking.company_id else self.env.company.id
            
            _logger.debug(
                "Validando holds para picking %s en compañía %s",
                picking.name,
                company_id
            )
            
            self._validate_picking_move_lines(picking, validator, company_id)
    
    def _validate_picking_move_lines(self, picking, validator, company_id):
        """
        Valida las move lines de un picking específico
        Solo considera holds de la misma compañía
        
        Args:
            picking: stock.picking record
            validator: HoldValidator instance
            company_id: int - ID de la empresa
            
        Raises:
            UserError: Si algún lote tiene hold de otro cliente en la misma compañía
        """
        for move_line in picking.move_line_ids:
            if not move_line.lot_id:
                continue
            
            # Buscar quant con hold activo en la misma compañía
            quant = self._find_quant_with_hold(
                move_line.lot_id.id,
                move_line.location_id.id,
                company_id
            )
            
            if quant and quant.x_hold_activo_id:
                # Verificar que el hold sea de la misma compañía
                if quant.x_hold_activo_id.company_id.id == company_id:
                    self._check_hold_customer_match(picking, move_line, quant, company_id)
    
    def _find_quant_with_hold(self, lot_id, location_id, company_id):
        """
        Busca quant con hold activo en la compañía especificada
        
        Args:
            lot_id: int - ID del lote
            location_id: int - ID de la ubicación
            company_id: int - ID de la empresa
            
        Returns:
            stock.quant: Quant con hold o None
        """
        quant = self.env['stock.quant'].search([
            ('lot_id', '=', lot_id),
            ('location_id', '=', location_id),
            ('company_id', '=', company_id),
            ('x_tiene_hold', '=', True),
        ], limit=1)
        
        if quant:
            _logger.debug(
                "Encontrado quant con hold: Lote=%s, Cliente=%s, Compañía=%s",
                quant.lot_id.name,
                quant.x_hold_para,
                quant.x_hold_activo_id.company_id.name if quant.x_hold_activo_id else 'N/A'
            )
        
        return quant
    
    def _check_hold_customer_match(self, picking, move_line, quant, company_id):
        """
        Verifica que el hold sea para el cliente correcto en la compañía correcta
        
        Args:
            picking: stock.picking record
            move_line: stock.move.line record
            quant: stock.quant record con hold
            company_id: int - ID de la empresa
            
        Raises:
            UserError: Si el hold es para otro cliente en la misma compañía
        """
        # Verificar que el partner coincida
        if picking.partner_id != quant.x_hold_activo_id.partner_id:
            company_name = self.env['res.company'].browse(company_id).name
            
            error_msg = (
                f"🔒 NO PUEDE VALIDAR ESTA ENTREGA\n\n"
                f"El lote '{move_line.lot_id.name}' está RESERVADO para:\n"
                f"👤 {quant.x_hold_para}\n"
                f"📅 Hasta: {quant.x_hold_expira.strftime('%d/%m/%Y %H:%M')}\n"
                f"⏱️ Días restantes: {quant.x_hold_dias_restantes}\n"
                f"🏢 Compañía: {company_name}\n\n"
                f"❌ Esta entrega es para '{picking.partner_id.name}'"
            )
            
            _logger.warning(
                "Intento de validar picking %s con lote reservado: "
                "Lote=%s, Hold para=%s, Picking para=%s, Compañía=%s",
                picking.name,
                move_line.lot_id.name,
                quant.x_hold_para,
                picking.partner_id.name,
                company_name
            )
            
            raise UserError(error_msg)```

## ./models/stock_quant.py
```py
# -*- coding: utf-8 -*-
# models/stock_quant.py
from odoo import models, fields, api
from odoo.exceptions import UserError
from .utils.plate_status_builder import PlateStatusBuilder
from .utils.bulk_hold_creator import BulkHoldCreator
from .utils.notification_builder import NotificationBuilder
from .utils.photo_helpers import PhotoHelper
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'
    
    # ==================== CAMPOS RELACIONADOS DEL LOTE ====================
    x_grosor = fields.Float(related='lot_id.x_grosor', string='Grosor', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', string='Alto', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', string='Ancho', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', string='Bloque', readonly=True)
    x_tipo = fields.Selection(related='lot_id.x_tipo', string='Tipo', readonly=True)
    x_atado = fields.Char(related='lot_id.x_atado', string='Atado', readonly=True)
    x_grupo = fields.Many2many(related='lot_id.x_grupo', string='Grupo', readonly=True)
    x_pedimento = fields.Char(related='lot_id.x_pedimento', string='Pedimento', readonly=True)
    x_contenedor = fields.Char(related='lot_id.x_contenedor', string='Contenedor', readonly=True)
    x_referencia_proveedor = fields.Char(related='lot_id.x_referencia_proveedor', string='Ref. Proveedor', readonly=True)
    x_fotografia_principal = fields.Binary(related='lot_id.x_fotografia_principal', readonly=True)
    x_cantidad_fotos = fields.Integer(related='lot_id.x_cantidad_fotos', readonly=True)
    x_detalles_placa = fields.Text(related='lot_id.x_detalles_placa', string='Detalles', readonly=True)
    
    # ==================== CAMPOS DE ESTADO DE RESERVA ====================
    x_esta_reservado = fields.Boolean(
        string='Reservado (Sistema)',
        compute='_compute_estado_reserva',
        store=True,
        help='Indica si el lote está reservado por el sistema de entregas'
    )
    
    x_en_orden_entrega = fields.Boolean(
        string='En Orden de Entrega',
        compute='_compute_estado_reserva',
        store=True,
        help='Indica si el lote está en una orden de entrega confirmada'
    )
    
    x_tiene_detalles = fields.Boolean(
        string='Tiene Detalles',
        compute='_compute_tiene_detalles',
        store=True,
        help='Indica si la placa tiene detalles especiales registrados'
    )
    
    # ==================== CAMPOS DE HOLD MANUAL ====================
    x_hold_ids = fields.One2many(
        'stock.lot.hold',
        'quant_id',
        string='Reservas Manuales',
        help='Holds/Reservas manuales de este quant'
    )
    
    x_tiene_hold = fields.Boolean(
        string='Tiene Hold',
        compute='_compute_estado_hold',
        store=True,
        help='Indica si el lote tiene una reserva manual activa'
    )
    
    x_hold_activo_id = fields.Many2one(
        'stock.lot.hold',
        string='Hold Activo',
        compute='_compute_estado_hold',
        store=True,
        help='Hold activo actualmente en este quant'
    )
    
    x_hold_para = fields.Char(
        string='Reservado Para',
        compute='_compute_estado_hold',
        store=True,
        help='Cliente para quien está reservado'
    )
    
    x_hold_expira = fields.Datetime(
        string='Expira',
        compute='_compute_estado_hold',
        store=True,
        help='Fecha de expiración del hold'
    )
    
    x_hold_dias_restantes = fields.Integer(
        string='Días Restantes',
        compute='_compute_estado_hold',
        help='Días hábiles restantes del hold'
    )
    
    # ==================== CAMPO DE ESTADO VISUAL ====================
    estado_placa = fields.Char(
        string='Estado Placa',
        compute='_compute_estado_placa',
        help='Estado visual de la placa (JSON para widget)'
    )
    
    # ==================== MÉTODOS COMPUTADOS ====================
    @api.depends('lot_id.x_detalles_placa')
    def _compute_tiene_detalles(self):
        """Verificar si la placa tiene detalles especiales"""
        for quant in self:
            quant.x_tiene_detalles = bool(
                quant.x_detalles_placa and 
                quant.x_detalles_placa.strip()
            )
    
    @api.depends('x_hold_ids.estado', 'x_hold_ids.fecha_expiracion', 'x_hold_ids.company_id', 'company_id')
    def _compute_estado_hold(self):
        """Computar el estado del hold manual de la compañía actual"""
        for quant in self:
            # Obtener compañía del quant
            company_id = quant.company_id.id if quant.company_id else self.env.company.id
            
            # Buscar hold activo de la misma compañía
            hold_activo = quant.x_hold_ids.filtered(
                lambda h: h.estado == 'activo' and h.company_id.id == company_id
            )
            
            if hold_activo:
                # Tomar el más reciente si hay múltiples
                hold_activo = hold_activo[0]
                quant.x_tiene_hold = True
                quant.x_hold_activo_id = hold_activo.id
                quant.x_hold_para = hold_activo.partner_id.name
                quant.x_hold_expira = hold_activo.fecha_expiracion
                quant.x_hold_dias_restantes = hold_activo.dias_restantes
            else:
                quant.x_tiene_hold = False
                quant.x_hold_activo_id = False
                quant.x_hold_para = False
                quant.x_hold_expira = False
                quant.x_hold_dias_restantes = 0
    
    @api.depends('reserved_quantity', 'quantity', 'lot_id')
    def _compute_estado_reserva(self):
        """Computar si el lote está reservado por el sistema de entregas"""
        for quant in self:
            quant.x_esta_reservado = quant.reserved_quantity > 0
            quant.x_en_orden_entrega = self._check_if_in_delivery_order(quant)
    
    def _check_if_in_delivery_order(self, quant):
        """Verifica si el lote está en una orden de entrega confirmada"""
        if not quant.lot_id or not quant.x_esta_reservado:
            return False
        
        move_line = self.env['stock.move.line'].search([
            ('lot_id', '=', quant.lot_id.id),
            ('location_id', '=', quant.location_id.id),
            ('state', 'in', ['assigned', 'partially_available']),
            ('picking_id.picking_type_code', '=', 'outgoing'),
        ], limit=1)
        
        return bool(move_line)
    
    @api.depends(
        'x_esta_reservado',
        'x_en_orden_entrega',
        'x_tiene_detalles',
        'x_detalles_placa',
        'x_tiene_hold',
        'x_hold_para',
        'x_hold_dias_restantes'
    )
    def _compute_estado_placa(self):
        """Generar JSON con los estados para el widget visual"""
        for quant in self:
            estados = self._build_plate_statuses(quant)
            quant.estado_placa = PlateStatusBuilder.to_json(estados)
    
    def _build_plate_statuses(self, quant):
        """Construye lista de estados de la placa"""
        estados = []
        
        # Hold manual (prioridad más alta)
        if quant.x_tiene_hold:
            estados.append(
                PlateStatusBuilder.build_hold_status(
                    quant.x_hold_para,
                    quant.x_hold_dias_restantes
                )
            )
        # Reserva del sistema (solo si no tiene hold)
        elif quant.x_esta_reservado and quant.x_en_orden_entrega:
            move_line = self._get_delivery_move_line(quant)
            if move_line:
                estados.append(
                    PlateStatusBuilder.build_delivery_status(
                        move_line.picking_id.name
                    )
                )
        
        # Detalles especiales
        if quant.x_tiene_detalles:
            estados.append(
                PlateStatusBuilder.build_details_status(quant.x_detalles_placa)
            )
        
        return estados
    
    def _get_delivery_move_line(self, quant):
        """Obtiene la move line de entrega asociada"""
        return self.env['stock.move.line'].search([
            ('lot_id', '=', quant.lot_id.id),
            ('location_id', '=', quant.location_id.id),
            ('state', 'in', ['assigned', 'partially_available']),
            ('picking_id.picking_type_code', '=', 'outgoing'),
        ], limit=1)
    
    # ==================== ACCIONES DE FOTOGRAFÍAS ====================
    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote"""
        self.ensure_one()
        
        if not self.lot_id:
            raise UserError('Este registro no tiene un lote asignado.')
        
        return {
            'name': f'Agregar Fotografía al Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lot_id': self.lot_id.id}
        }
    
    def action_view_lot_photos(self):
        """Ver las fotografías del lote"""
        self.ensure_one()
        
        if not self.lot_id:
            raise UserError('Este registro no tiene un lote asignado.')
        
        return PhotoHelper.build_photo_gallery_action(self.lot_id.id, self.lot_id.name)
    
    # ==================== ACCIONES DE HOLD ====================
    def action_crear_hold(self):
        """Abrir wizard para crear un hold manual en este quant"""
        self.ensure_one()
        
        if not self.lot_id:
            raise UserError('Este registro no tiene un lote asignado.')
        
        if self.x_tiene_hold:
            dias_texto = (
                f'{self.x_hold_dias_restantes} días hábiles' 
                if self.x_hold_dias_restantes != 1 
                else '1 día hábil'
            )
            raise UserError(
                f'Este lote ya tiene una reserva activa para {self.x_hold_para} '
                f'que expira en {dias_texto}.'
            )
        
        return {
            'name': f'Reservar Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.hold.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_quant_id': self.id,
                'default_lot_id': self.lot_id.id,
            }
        }
    
    def action_ver_hold(self):
        """Ver detalles del hold activo"""
        self.ensure_one()
        
        if not self.x_hold_activo_id:
            raise UserError('Este lote no tiene una reserva activa.')
        
        return {
            'name': f'Reserva del Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.hold',
            'view_mode': 'form',
            'res_id': self.x_hold_activo_id.id,
            'target': 'new',
        }
    
    def action_cancelar_hold(self):
        """Cancelar el hold activo"""
        self.ensure_one()
        
        if not self.x_hold_activo_id:
            raise UserError('Este lote no tiene una reserva activa.')
        
        self.x_hold_activo_id.action_cancelar_hold()
        
        return NotificationBuilder.build_success(
            '¡Éxito!',
            f'Reserva cancelada para el lote {self.lot_id.name}'
        )
    
    # ==================== MÉTODOS DE API (BÁSICOS) ====================
    @api.model
    def get_current_user_info(self):
        """Obtener información del usuario actual"""
        return {
            'id': self.env.user.id,
            'name': self.env.user.name
        }
    
    @api.model
    def sync_cart_to_session(self, items):
        """Sincronizar carrito desde frontend a BD"""
        cart_model = self.env['shopping.cart']
        cart_model.clear_cart()
        
        for item in items:
            cart_model.add_to_cart(
                quant_id=item['id'],
                lot_id=item['lot_id'],
                product_id=item['product_id'],
                quantity=item['quantity'],
                location_name=item['location_name']
            )
        
        return {'success': True}
    
    @api.model
    def create_holds_from_cart(self, partner_id=None, project_id=None, 
                               architect_id=None, selected_lots=None, 
                               notes=None, currency_code='USD', 
                               product_prices=None):
        """Crear holds múltiples desde el carrito con información de precios"""
        creator = BulkHoldCreator(self.env)
        
        return creator.create_holds_from_cart(
            partner_id=partner_id,
            project_id=project_id,
            architect_id=architect_id,
            selected_lots=selected_lots,
            notes=notes,
            currency_code=currency_code,
            product_prices=product_prices
        )
    
    # ==================== OVERRIDE CRÍTICO - FILTRADO DE QUANTS ====================
    def _gather(self, product_id, location_id, lot_id=None, package_id=None, 
                owner_id=None, strict=False, qty=None):
        """
        Override para filtrar quants con holds antes de asignación FIFO/LIFO
        
        Solo incluye quants:
        - Sin hold, o
        - Con hold para el cliente permitido en contexto
        - Considerando la compañía del contexto
        """
        # Llamar al método original
        quants = super(StockQuant, self)._gather(
            product_id, location_id, lot_id=lot_id, package_id=package_id,
            owner_id=owner_id, strict=strict, qty=qty
        )
        
        # Filtrar por holds si hay cliente permitido en contexto
        return self._filter_quants_by_hold(quants)
    
    def _filter_quants_by_hold(self, quants):
        """
        Filtra quants según holds del cliente permitido Y compañía
        
        Args:
            quants: recordset de stock.quant
            
        Returns:
            recordset: Quants filtrados
        """
        cliente_permitido_id = self._context.get('allowed_partner_id')
        company_id = self._context.get('company_id') or self.env.company.id
        
        # Sin cliente en contexto → retornar todos
        if not cliente_permitido_id:
            return quants
        
        quants_validos = self.env['stock.quant']
        
        for quant in quants:
            if self._is_quant_available_for_customer(quant, cliente_permitido_id, company_id):
                quants_validos |= quant
        
        return quants_validos
    
    def _is_quant_available_for_customer(self, quant, customer_id, company_id):
        """
        Verifica si un quant está disponible para un cliente considerando compañía
        
        Args:
            quant: stock.quant record
            customer_id: int - ID del cliente
            company_id: int - ID de la compañía
            
        Returns:
            bool: True si está disponible
        """
        # Sin hold → disponible para todos
        if not quant.x_tiene_hold:
            return True
        
        # Con hold → verificar cliente Y compañía
        if quant.x_hold_activo_id:
            # Verificar que el hold sea de la misma compañía
            if quant.x_hold_activo_id.company_id.id != company_id:
                return True  # Hold de otra compañía no aplica, el lote está disponible
            
            # Hold de la misma compañía → verificar cliente
            hold_partner_id = quant.x_hold_activo_id.partner_id.id
            return hold_partner_id == customer_id
        
        return False
    
    # ==================== MÉTODOS PARA INVENTARIO VISUAL ====================
    
    @api.model
    def get_inventory_grouped_by_product(self, filters=None):
        """
        Obtener inventario agrupado por producto con filtros avanzados
        
        Args:
            filters: dict - Diccionario con filtros aplicados
            
        Returns:
            list: Lista de productos con inventario agrupado
        """
        domain = [('quantity', '>', 0)]
        
        # Aplicar filtros dinámicos
        if filters:
            domain = self._build_filter_domain(domain, filters)
        
        # Buscar quants que cumplan el dominio
        quants = self.search(domain)
        
        # Agrupar por producto y calcular métricas
        products_data = self._group_quants_by_product(quants)
        
        # Convertir a lista y ordenar
        result = list(products_data.values())
        result.sort(key=lambda x: x['product_name'])
        
        return result
    
    def _build_filter_domain(self, domain, filters):
        """
        Construye el dominio de búsqueda según filtros
        
        Args:
            domain: list - Dominio base
            filters: dict - Filtros a aplicar
            
        Returns:
            list: Dominio actualizado
        """
        if filters.get('product_name'):
            search_term = filters['product_name'].strip()
            domain.append('|')
            domain.append(('product_id.name', 'ilike', search_term))
            domain.append(('product_id.default_code', 'ilike', search_term))
        
        if filters.get('almacen_id'):
            try:
                almacen = self.env['stock.warehouse'].browse(int(filters['almacen_id']))
                if almacen.view_location_id:
                    domain.append(('location_id', 'child_of', almacen.view_location_id.id))
            except (ValueError, TypeError):
                pass
        
        if filters.get('ubicacion_id'):
            try:
                domain.append(('location_id', '=', int(filters['ubicacion_id'])))
            except (ValueError, TypeError):
                pass
        
        if filters.get('tipo'):
            domain.append(('x_tipo', '=', filters['tipo']))
        
        if filters.get('categoria_id'):
            try:
                domain.append(('product_id.categ_id', 'child_of', int(filters['categoria_id'])))
            except (ValueError, TypeError):
                pass
        
        if filters.get('grupo'):
            domain.append(('x_grupo', '=', filters['grupo']))
        
        if filters.get('acabado'):
            domain.append(('x_acabado', '=', filters['acabado']))
        
        if filters.get('grosor'):
            domain.append(('x_grosor', '=', filters['grosor']))
        
        if filters.get('numero_serie'):
            domain.append(('lot_id.name', 'ilike', filters['numero_serie']))
        
        if filters.get('bloque'):
            domain.append(('x_bloque', 'ilike', filters['bloque']))
        
        if filters.get('pedimento'):
            domain.append(('x_pedimento', 'ilike', filters['pedimento']))
        
        if filters.get('contenedor'):
            domain.append(('x_contenedor', 'ilike', filters['contenedor']))
        
        if filters.get('atado'):
            domain.append(('x_atado', 'ilike', filters['atado']))
        
        return domain
    
    def _group_quants_by_product(self, quants):
        """
        Agrupa quants por producto y calcula métricas
        
        Args:
            quants: recordset - Quants a agrupar
            
        Returns:
            defaultdict: Diccionario con productos agrupados
        """
        products_data = defaultdict(lambda: {
            'stock_qty': 0.0,
            'stock_plates': 0,
            'hold_qty': 0.0,
            'hold_plates': 0,
            'committed_qty': 0.0,
            'committed_plates': 0,
            'available_qty': 0.0,
            'available_plates': 0,
            'total_qty': 0.0,
            'quant_ids': [],
            'has_details': False,
            'has_photos': False,
            'plate_area': 0.0,
        })
        
        for quant in quants:
            product = quant.product_id
            key = product.id
            
            # Calcular área de placa
            plate_area = self._calculate_plate_area(quant)
            
            # Verificar hold activo
            hold_activo = self.env['stock.lot.hold'].search([
                ('quant_id', '=', quant.id),
                ('estado', '=', 'activo')
            ], limit=1)
            
            # Calcular cantidades
            metrics = self._calculate_quant_metrics(quant, hold_activo, plate_area)
            
            # Acumular en el producto
            self._accumulate_product_metrics(products_data[key], metrics, quant, product, plate_area)
        
        return products_data
    
    def _calculate_plate_area(self, quant):
        """Calcula el área de una placa"""
        if hasattr(quant, 'x_alto') and hasattr(quant, 'x_ancho'):
            if quant.x_alto and quant.x_ancho:
                try:
                    return float(quant.x_alto) * float(quant.x_ancho)
                except (ValueError, TypeError):
                    pass
        return 0.0
    
    def _calculate_quant_metrics(self, quant, hold_activo, plate_area):
        """
        Calcula métricas individuales de un quant
        
        Args:
            quant: stock.quant record
            hold_activo: stock.lot.hold record or False
            plate_area: float - Área de la placa
            
        Returns:
            dict: Diccionario con métricas calculadas
        """
        total_m2 = quant.quantity
        hold_m2 = total_m2 if hold_activo else 0.0
        committed_m2 = quant.reserved_quantity
        stock_m2 = total_m2
        available_m2 = total_m2 - hold_m2 - committed_m2
        
        total_plates = 0
        hold_plates = 0
        committed_plates = 0
        stock_plates = 0
        available_plates = 0
        
        if plate_area > 0:
            total_plates = int(round(total_m2 / plate_area))
            hold_plates = 1 if hold_activo else 0
            committed_plates = int(round(committed_m2 / plate_area))
            stock_plates = total_plates
            available_plates = stock_plates - hold_plates - committed_plates
        
        return {
            'stock_m2': stock_m2,
            'stock_plates': stock_plates,
            'hold_m2': hold_m2,
            'hold_plates': hold_plates,
            'committed_m2': committed_m2,
            'committed_plates': committed_plates,
            'available_m2': available_m2,
            'available_plates': available_plates,
            'total_m2': total_m2,
        }
    
    def _accumulate_product_metrics(self, product_data, metrics, quant, product, plate_area):
        """
        Acumula métricas en los datos del producto
        
        Args:
            product_data: dict - Datos acumulados del producto
            metrics: dict - Métricas del quant actual
            quant: stock.quant record
            product: product.product record
            plate_area: float - Área de la placa
        """
        # Información básica del producto (solo la primera vez)
        if 'product_id' not in product_data:
            category_name = self._get_category_name(product)
            tipo = self._get_tipo_display(quant)
            
            product_data.update({
                'product_id': product.id,
                'product_name': product.display_name,
                'product_code': product.default_code or '',
                'uom_name': product.uom_id.name,
                'categ_name': category_name,
                'tipo': tipo,
            })
        
        # Acumular métricas
        product_data['stock_qty'] += metrics['stock_m2']
        product_data['stock_plates'] += metrics['stock_plates']
        product_data['hold_qty'] += metrics['hold_m2']
        product_data['hold_plates'] += metrics['hold_plates']
        product_data['committed_qty'] += metrics['committed_m2']
        product_data['committed_plates'] += metrics['committed_plates']
        product_data['available_qty'] += metrics['available_m2']
        product_data['available_plates'] += metrics['available_plates']
        product_data['total_qty'] += metrics['total_m2']
        product_data['quant_ids'].append(quant.id)
        
        # Área de placa (solo la primera vez)
        if plate_area > 0 and product_data['plate_area'] == 0:
            product_data['plate_area'] = plate_area
        
        # Flags de contenido
        if hasattr(quant, 'x_tiene_detalles') and quant.x_tiene_detalles:
            product_data['has_details'] = True
        if hasattr(quant, 'x_cantidad_fotos') and quant.x_cantidad_fotos > 0:
            product_data['has_photos'] = True
    
    def _get_category_name(self, product):
        """Obtiene el nombre de la categoría más específica"""
        if not product.categ_id:
            return ''
        
        current_categ = product.categ_id
        while current_categ.child_id and len(current_categ.child_id) > 0:
            current_categ = current_categ.child_id[0]
        
        return current_categ.name
    
    def _get_tipo_display(self, quant):
        """Obtiene el valor display del campo selection x_tipo"""
        if not hasattr(quant, 'x_tipo') or not quant.x_tipo:
            return ''
        
        selection = quant._fields['x_tipo'].selection
        if callable(selection):
            selection = selection(quant)
        
        return dict(selection).get(quant.x_tipo, '')
    
    @api.model
    def get_quant_details(self, quant_ids):
        """
        Obtener detalles expandidos de quants específicos
        
        Args:
            quant_ids: list - Lista de IDs de quants
            
        Returns:
            list: Lista de diccionarios con detalles de cada quant
        """
        if not quant_ids:
            return []
        
        quants = self.browse(quant_ids)
        details = []
        
        for quant in quants:
            detail = self._build_quant_detail(quant)
            details.append(detail)
        
        return details
    
    def _build_quant_detail(self, quant):
        """
        Construye el diccionario de detalles de un quant
        
        Args:
            quant: stock.quant record
            
        Returns:
            dict: Diccionario con todos los detalles del quant
        """
        # Campos básicos
        grosor = getattr(quant, 'x_grosor', None) or ''
        alto = getattr(quant, 'x_alto', None) or ''
        ancho = getattr(quant, 'x_ancho', None) or ''
        bloque = getattr(quant, 'x_bloque', None) or ''
        atado = getattr(quant, 'x_atado', None) or ''
        
        # Tipo (selection field)
        tipo = self._get_tipo_display(quant)
        
        # Campos logísticos
        pedimento = getattr(quant, 'x_pedimento', None) or ''
        contenedor = getattr(quant, 'x_contenedor', None) or ''
        referencia_proveedor = getattr(quant, 'x_referencia_proveedor', None) or ''
        
        # Calcular área y placas
        plate_area = self._calculate_plate_area(quant)
        plates_info = self._calculate_plates_info(quant, plate_area)
        
        # Estados
        states = self._get_quant_states(quant)
        
        # Hold info
        hold_info = self._get_hold_info(quant)
        
        # Fotos y detalles
        content_info = self._get_content_info(quant)
        
        # Sales person
        sales_person = self._get_sales_person(quant)
        
        return {
            'id': quant.id,
            'location_name': quant.location_id.complete_name,
            'lot_name': quant.lot_id.name if quant.lot_id else '',
            'quantity': quant.quantity,
            'reserved_quantity': quant.reserved_quantity,
            'available_quantity': quant.quantity - quant.reserved_quantity,
            'total_plates': plates_info['total_plates'],
            'committed_plates': plates_info['committed_plates'],
            'available_plates': plates_info['available_plates'],
            'grosor': grosor,
            'alto': alto,
            'ancho': ancho,
            'bloque': bloque,
            'atado': atado,
            'tipo': tipo,
            'pedimento': pedimento,
            'contenedor': contenedor,
            'referencia_proveedor': referencia_proveedor,
            'esta_reservado': states['esta_reservado'],
            'en_orden_entrega': states['en_orden_entrega'],
            'en_orden_venta': states['en_orden_venta'],
            'sale_order_ids': states['sale_order_ids'],
            'tiene_detalles': content_info['tiene_detalles'],
            'tiene_hold': hold_info['tiene_hold'],
            'hold_info': hold_info['hold_data'],
            'cantidad_fotos': content_info['cantidad_fotos'],
            'detalles_placa': content_info['detalles_placa'],
            'sales_person': sales_person,
        }
    
    def _calculate_plates_info(self, quant, plate_area):
        """Calcula información de placas"""
        total_plates = 0
        committed_plates = 0
        available_plates = 0
        
        if plate_area > 0:
            total_plates = int(round(quant.quantity / plate_area))
            committed_plates = int(round(quant.reserved_quantity / plate_area))
            available_plates = total_plates - committed_plates
        
        return {
            'total_plates': total_plates,
            'committed_plates': committed_plates,
            'available_plates': available_plates,
        }
    
    def _get_quant_states(self, quant):
        """Obtiene estados del quant (reservas, órdenes, etc)"""
        esta_reservado = quant.reserved_quantity > 0
        
        # Verificar orden de entrega
        en_orden_entrega = False
        if quant.lot_id:
            delivery_moves = self.env['stock.move.line'].search([
                ('lot_id', '=', quant.lot_id.id),
                ('state', 'in', ['assigned', 'done']),
                ('picking_id.picking_type_id.code', '=', 'outgoing')
            ], limit=1)
            en_orden_entrega = bool(delivery_moves)
        
        # Verificar órdenes de venta
        en_orden_venta = False
        sale_order_ids = []
        if quant.lot_id:
            sale_moves = self.env['stock.move.line'].search([
                ('lot_id', '=', quant.lot_id.id),
                ('state', 'in', ['assigned', 'partially_available', 'done']),
                ('move_id.sale_line_id', '!=', False)
            ])
            
            if sale_moves:
                en_orden_venta = True
                for move in sale_moves:
                    if move.move_id.sale_line_id and move.move_id.sale_line_id.order_id:
                        so = move.move_id.sale_line_id.order_id
                        if so.id not in sale_order_ids:
                            sale_order_ids.append(so.id)
        
        return {
            'esta_reservado': esta_reservado,
            'en_orden_entrega': en_orden_entrega,
            'en_orden_venta': en_orden_venta,
            'sale_order_ids': sale_order_ids,
        }
    
    def _get_hold_info(self, quant):
        """Obtiene información de hold activo"""
        tiene_hold = False
        hold_data = {}
        
        if quant.lot_id:
            hold = self.env['stock.lot.hold'].search([
                ('quant_id', '=', quant.id),
                ('estado', '=', 'activo')
            ], limit=1)
            
            if hold:
                tiene_hold = True
                
                proyecto_nombre = ''
                if hasattr(hold, 'project_id') and hold.project_id:
                    proyecto_nombre = hold.project_id.name
                
                arquitecto_nombre = ''
                if hasattr(hold, 'arquitecto_id') and hold.arquitecto_id:
                    arquitecto_nombre = hold.arquitecto_id.name
                
                vendedor_nombre = ''
                if hasattr(hold, 'user_id') and hold.user_id:
                    vendedor_nombre = hold.user_id.name
                
                hold_data = {
                    'id': hold.id,
                    'partner_name': hold.partner_id.name,
                    'fecha_inicio': hold.fecha_inicio.strftime('%d/%m/%Y %H:%M') if hold.fecha_inicio else '',
                    'fecha_expiracion': hold.fecha_expiracion.strftime('%d/%m/%Y %H:%M') if hold.fecha_expiracion else '',
                    'notas': hold.notas or '',
                    'proyecto_nombre': proyecto_nombre,
                    'arquitecto_nombre': arquitecto_nombre,
                    'vendedor_nombre': vendedor_nombre,
                }
        
        return {
            'tiene_hold': tiene_hold,
            'hold_data': hold_data,
        }
    
    def _get_content_info(self, quant):
        """Obtiene información de contenido (fotos, notas)"""
        tiene_detalles = getattr(quant, 'x_tiene_detalles', False) or False
        
        cantidad_fotos = 0
        if quant.lot_id:
            fotos = self.env['stock.lot.image'].search_count([
                ('lot_id', '=', quant.lot_id.id)
            ])
            cantidad_fotos = fotos
        
        detalles_placa = ''
        if quant.lot_id and hasattr(quant.lot_id, 'x_detalles_placa'):
            detalles_placa = quant.lot_id.x_detalles_placa or ''
        
        return {
            'tiene_detalles': tiene_detalles,
            'cantidad_fotos': cantidad_fotos,
            'detalles_placa': detalles_placa,
        }
    
    def _get_sales_person(self, quant):
        """Obtiene información del vendedor"""
        sales_person = ''
        if quant.lot_id and hasattr(quant.lot_id, 'x_sales_person_id'):
            if quant.lot_id.x_sales_person_id:
                sales_person = quant.lot_id.x_sales_person_id.name
        return sales_person
    
    # ==================== MÉTODOS DE FOTOGRAFÍAS ====================
    
    @api.model
    def get_lot_photos(self, quant_id=None):
        """
        Obtener fotografías de un lote
        
        Args:
            quant_id: int - ID del quant
            
        Returns:
            dict: Información del lote y sus fotografías
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            photos = self.env['stock.lot.image'].search([
                ('lot_id', '=', quant.lot_id.id)
            ], order='sequence, id')
            
            photos_data = []
            for photo in photos:
                photos_data.append({
                    'id': photo.id,
                    'name': photo.name,
                    'image': photo.image,
                    'sequence': photo.sequence,
                    'notas': photo.notas or '',
                    'fecha_captura': photo.fecha_captura.strftime('%d/%m/%Y %H:%M') if photo.fecha_captura else '',
                })
            
            result = {
                'lot_id': quant.lot_id.id,
                'lot_name': quant.lot_id.name,
                'product_name': quant.product_id.name,
                'photos': photos_data,
            }
            
            return result
            
        except Exception as e:
            return {'error': f'Error interno: {str(e)}'}
    
    @api.model
    def save_lot_photo(self, quant_id=None, photo_name='', photo_data='', sequence=10, notas=''):
        """
        Guardar una nueva fotografía en un lote
        
        Args:
            quant_id: int - ID del quant
            photo_name: str - Nombre de la foto
            photo_data: str - Datos base64 de la imagen
            sequence: int - Orden de la foto
            notas: str - Notas adicionales
            
        Returns:
            dict: Resultado de la operación
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            photo = self.env['stock.lot.image'].create({
                'lot_id': quant.lot_id.id,
                'name': photo_name,
                'image': photo_data,
                'sequence': sequence,
                'notas': notas,
            })
            
            return {
                'success': True,
                'photo_id': photo.id,
                'message': f'Foto agregada correctamente al lote {quant.lot_id.name}'
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    @api.model
    def delete_lot_photo(self, photo_id):
        """
        Eliminar una fotografía
        
        Args:
            photo_id: int - ID de la foto a eliminar
            
        Returns:
            dict: Resultado de la operación
        """
        try:
            photo = self.env['stock.lot.image'].browse(photo_id)
            
            if not photo.exists():
                return {'error': 'Foto no encontrada'}
            
            photo.unlink()
            
            return {
                'success': True,
                'message': 'Foto eliminada correctamente'
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    # ==================== MÉTODOS DE NOTAS ====================
    
    @api.model
    def get_lot_notes(self, quant_id=None):
        """
        Obtener notas de un lote
        
        Args:
            quant_id: int - ID del quant
            
        Returns:
            dict: Información del lote y sus notas
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            notes = quant.lot_id.x_detalles_placa or ''
            
            result = {
                'lot_id': quant.lot_id.id,
                'lot_name': quant.lot_id.name,
                'product_name': quant.product_id.name,
                'notes': notes,
            }
            
            return result
            
        except Exception as e:
            return {'error': f'Error interno: {str(e)}'}
    
    @api.model
    def save_lot_notes(self, quant_id=None, notes=''):
        """
        Guardar notas de un lote
        
        Args:
            quant_id: int - ID del quant
            notes: str - Notas a guardar
            
        Returns:
            dict: Resultado de la operación
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            quant.lot_id.write({
                'x_detalles_placa': notes
            })
            
            return {
                'success': True,
                'message': f'Notas guardadas correctamente para el lote {quant.lot_id.name}'
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    # ==================== MÉTODOS DE HISTORIAL ====================
    
    @api.model
    def get_lot_history(self, quant_id=None):
        """
        Obtener historial completo de un lote
        
        Args:
            quant_id: int - ID del quant
            
        Returns:
            dict: Información histórica completa del lote
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            lot = quant.lot_id
            
            # Información general
            general_info = self._build_general_info(quant, lot)
            
            # Información de compras
            purchase_info = self._get_purchase_info(lot)
            
            # Movimientos
            movements = self._get_movements(lot)
            
            # Órdenes de venta
            sales_orders = self._get_sales_orders(lot)
            
            # Reservas y apartados
            reservations = self._get_reservations(quant, lot)
            
            # Entregas
            deliveries = self._get_deliveries(lot)
            
            # Estadísticas
            statistics = self._calculate_statistics(movements, sales_orders, reservations, deliveries, lot)
            
            result = {
                'general_info': general_info,
                'purchase_info': purchase_info,
                'movements': movements,
                'sales_orders': sales_orders,
                'reservations': reservations,
                'deliveries': deliveries,
                'statistics': statistics,
            }
            
            return result
            
        except Exception as e:
            return {'error': f'Error interno: {str(e)}'}
    
    def _build_general_info(self, quant, lot):
        """Construye información general del lote"""
        estado_actual = 'Disponible'
        
        if quant.reserved_quantity > 0:
            estado_actual = 'Reservado'
        
        hold_activo = self.env['stock.lot.hold'].search([
            ('quant_id', '=', quant.id),
            ('estado', '=', 'activo')
        ], limit=1)
        
        if hold_activo:
            estado_actual = 'Apartado (Hold)'
        
        return {
            'lot_name': lot.name,
            'product_name': quant.product_id.name,
            'product_code': quant.product_id.default_code or '',
            'fecha_creacion': lot.create_date.strftime('%d/%m/%Y %H:%M') if lot.create_date else '',
            'estado_actual': estado_actual,
            'cantidad_actual': quant.quantity,
            'cantidad_reservada': quant.reserved_quantity,
            'cantidad_disponible': quant.quantity - quant.reserved_quantity,
            'ubicacion_actual': quant.location_id.complete_name,
        }
    
    def _get_purchase_info(self, lot):
        """Obtiene información de compras del lote"""
        purchase_info = []
        
        incoming_moves = self.env['stock.move.line'].search([
            ('lot_id', '=', lot.id),
            ('picking_id.picking_type_id.code', '=', 'incoming')
        ])
        
        po_line_ids = set()
        for move_line in incoming_moves:
            if move_line.move_id and move_line.move_id.purchase_line_id:
                po_line_ids.add(move_line.move_id.purchase_line_id.id)
        
        if po_line_ids:
            purchase_lines = self.env['purchase.order.line'].browse(list(po_line_ids))
            valid_lines = [pl for pl in purchase_lines if pl.order_id and pl.order_id.state in ['purchase', 'done']]
            valid_lines.sort(key=lambda x: x.order_id.date_order if x.order_id.date_order else fields.Datetime.now(), reverse=True)
            
            for po_line in valid_lines[:5]:
                purchase_info.append({
                    'orden_compra': po_line.order_id.name,
                    'proveedor': po_line.order_id.partner_id.name,
                    'fecha_orden': po_line.order_id.date_order.strftime('%d/%m/%Y') if po_line.order_id.date_order else '',
                    'cantidad': po_line.product_qty,
                    'precio_unitario': po_line.price_unit,
                    'total': po_line.price_subtotal,
                    'moneda': po_line.order_id.currency_id.symbol,
                    'estado': dict(po_line.order_id._fields['state'].selection).get(po_line.order_id.state),
                })
        
        return purchase_info
    
    def _get_movements(self, lot):
        """Obtiene movimientos del lote"""
        movements = []
        
        stock_moves = self.env['stock.move.line'].search([
            ('lot_id', '=', lot.id)
        ], order='date desc', limit=50)
        
        for move in stock_moves:
            movement_type = 'Otro'
            icon = 'fa-exchange'
            color = 'secondary'
            
            if move.picking_id:
                picking_code = move.picking_id.picking_type_id.code
                if picking_code == 'incoming':
                    movement_type = 'Entrada'
                    icon = 'fa-arrow-down'
                    color = 'success'
                elif picking_code == 'outgoing':
                    movement_type = 'Salida'
                    icon = 'fa-arrow-up'
                    color = 'danger'
                elif picking_code == 'internal':
                    movement_type = 'Movimiento Interno'
                    icon = 'fa-exchange'
                    color = 'info'
            
            movements.append({
                'fecha': move.date.strftime('%d/%m/%Y %H:%M') if move.date else '',
                'tipo': movement_type,
                'icon': icon,
                'color': color,
                'origen': move.location_id.name,
                'destino': move.location_dest_id.name,
                'cantidad': move.qty_done,
                'referencia': move.picking_id.name if move.picking_id else move.reference or '-',
                'usuario': move.create_uid.name if move.create_uid else '-',
            })
        
        return movements
    
    def _get_sales_orders(self, lot):
        """Obtiene órdenes de venta del lote"""
        sales_orders = []
        
        outgoing_moves = self.env['stock.move.line'].search([
            ('lot_id', '=', lot.id),
            ('picking_id.picking_type_id.code', '=', 'outgoing')
        ])
        
        so_line_ids = set()
        for move_line in outgoing_moves:
            if move_line.move_id and move_line.move_id.sale_line_id:
                so_line_ids.add(move_line.move_id.sale_line_id.id)
        
        if so_line_ids:
            sale_lines = self.env['sale.order.line'].browse(list(so_line_ids))
            valid_lines = [sl for sl in sale_lines if sl.order_id and sl.order_id.state in ['sale', 'done']]
            valid_lines.sort(key=lambda x: x.order_id.date_order if x.order_id.date_order else fields.Datetime.now(), reverse=True)
            
            for so_line in valid_lines[:10]:
                sales_orders.append({
                    'orden_venta': so_line.order_id.name,
                    'cliente': so_line.order_id.partner_id.name,
                    'vendedor': so_line.order_id.user_id.name if so_line.order_id.user_id else '-',
                    'fecha_orden': so_line.order_id.date_order.strftime('%d/%m/%Y') if so_line.order_id.date_order else '',
                    'cantidad': so_line.product_uom_qty,
                    'precio_unitario': so_line.price_unit,
                    'total': so_line.price_subtotal,
                    'moneda': so_line.order_id.currency_id.symbol,
                    'estado': dict(so_line.order_id._fields['state'].selection).get(so_line.order_id.state),
                })
        
        return sales_orders
    
    def _get_reservations(self, quant, lot):
        """Obtiene reservas y apartados del lote"""
        reservations = []
        
        # Holds manuales
        holds = self.env['stock.lot.hold'].search([
            ('quant_id', '=', quant.id)
        ], order='fecha_inicio desc')
        
        for hold in holds:
            reservations.append({
                'tipo': 'Apartado (Hold)',
                'partner': hold.partner_id.name,
                'fecha_inicio': hold.fecha_inicio.strftime('%d/%m/%Y %H:%M') if hold.fecha_inicio else '',
                'fecha_expiracion': hold.fecha_expiracion.strftime('%d/%m/%Y %H:%M') if hold.fecha_expiracion else '',
                'estado': 'Activo' if hold.estado == 'activo' else 'Liberado',
                'notas': hold.notas or '',
                'color': 'warning' if hold.estado == 'activo' else 'secondary'
            })
        
        # Reservas del sistema
        reserved_move_lines = self.env['stock.move.line'].search([
            ('product_id', '=', quant.product_id.id),
            ('lot_id', '=', lot.id),
            ('state', 'in', ['assigned', 'partially_available']),
            ('quantity', '>', 0)
        ])
        
        for move_line in reserved_move_lines:
            partner_name = '-'
            move = move_line.move_id
            
            if move:
                if move.sale_line_id and move.sale_line_id.order_id:
                    partner_name = move.sale_line_id.order_id.partner_id.name
                elif move.picking_id and move.picking_id.partner_id:
                    partner_name = move.picking_id.partner_id.name
            
            reservations.append({
                'tipo': 'Reserva de Stock',
                'partner': partner_name,
                'fecha_inicio': move_line.date.strftime('%d/%m/%Y %H:%M') if move_line.date else '',
                'fecha_expiracion': '-',
                'estado': 'Activo',
                'notas': move_line.picking_id.name if move_line.picking_id else move_line.reference or '',
                'color': 'info'
            })
        
        return reservations
    
    def _get_deliveries(self, lot):
        """Obtiene entregas del lote"""
        deliveries = []
        
        delivery_moves = self.env['stock.move.line'].search([
            ('lot_id', '=', lot.id),
            ('picking_id.picking_type_id.code', '=', 'outgoing')
        ], order='date desc')
        
        for move in delivery_moves:
            picking = move.picking_id
            if picking:
                deliveries.append({
                    'referencia': picking.name,
                    'cliente': picking.partner_id.name if picking.partner_id else '-',
                    'fecha_programada': picking.scheduled_date.strftime('%d/%m/%Y') if picking.scheduled_date else '',
                    'fecha_efectiva': picking.date_done.strftime('%d/%m/%Y %H:%M') if picking.date_done else '-',
                    'cantidad': move.qty_done,
                    'estado': dict(picking._fields['state'].selection).get(picking.state),
                    'origen': picking.origin or '-',
                    'color': 'success' if picking.state == 'done' else 'warning' if picking.state == 'assigned' else 'secondary'
                })
        
        return deliveries
    
    def _calculate_statistics(self, movements, sales_orders, reservations, deliveries, lot):
        """Calcula estadísticas del lote"""
        dias_en_inventario = 0
        if lot.create_date:
            dias_en_inventario = (fields.Datetime.now() - lot.create_date).days
        
        return {
            'total_movimientos': len(movements),
            'total_entradas': len([m for m in movements if m['tipo'] == 'Entrada']),
            'total_salidas': len([m for m in movements if m['tipo'] == 'Salida']),
            'total_ventas': len(sales_orders),
            'total_apartados': len(reservations),
            'total_entregas': len(deliveries),
            'dias_en_inventario': dias_en_inventario,
        }
    
    # ==================== MÉTODOS DE ÓRDENES DE VENTA ====================
    
    @api.model
    def get_sale_order_info(self, sale_order_ids=None):
        """
        Obtener información de órdenes de venta
        
        Args:
            sale_order_ids: list - Lista de IDs de órdenes de venta
            
        Returns:
            dict: Información de las órdenes de venta
        """
        if not sale_order_ids:
            return {'error': 'IDs de órdenes de venta inválidos'}
        
        try:
            sale_orders = self.env['sale.order'].browse(sale_order_ids)
            orders_data = []
            
            for so in sale_orders:
                if not so.exists():
                    continue
                
                orders_data.append({
                    'id': so.id,
                    'name': so.name,
                    'partner_name': so.partner_id.name,
                    'partner_id': so.partner_id.id,
                    'date_order': so.date_order.strftime('%d/%m/%Y') if so.date_order else '',
                    'amount_total': so.amount_total,
                    'currency_symbol': so.currency_id.symbol,
                    'state': so.state,
                    'state_display': dict(so._fields['state'].selection).get(so.state),
                    'user_name': so.user_id.name if so.user_id else '',
                    'commitment_date': so.commitment_date.strftime('%d/%m/%Y') if so.commitment_date else '',
                })
            
            result = {
                'orders': orders_data,
                'count': len(orders_data),
            }
            
            return result
            
        except Exception as e:
            return {'error': f'Error interno: {str(e)}'}
    
    # ==================== MÉTODOS DE HOLD AVANZADOS ====================
    
    @api.model
    def create_lot_hold(self, quant_id=None, partner_id=None, notas=''):
        """
        Crear un hold básico (versión simple)
        
        Args:
            quant_id: int - ID del quant
            partner_id: int - ID del cliente
            notas: str - Notas adicionales
            
        Returns:
            dict: Resultado de la operación
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        if not partner_id:
            return {'error': 'Debe seleccionar un cliente'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            hold_existente = self.env['stock.lot.hold'].search([
                ('quant_id', '=', quant.id),
                ('estado', '=', 'activo')
            ], limit=1)
            
            if hold_existente:
                return {
                    'error': f'Este lote ya tiene una reserva activa para {hold_existente.partner_id.name}'
                }
            
            hold = self.env['stock.lot.hold'].create({
                'lot_id': quant.lot_id.id,
                'quant_id': quant.id,
                'partner_id': partner_id,
                'notas': notas or '',
            })
            
            return {
                'success': True,
                'hold_id': hold.id,
                'message': f'Lote {quant.lot_id.name} apartado para {hold.partner_id.name} hasta {hold.fecha_expiracion.strftime("%d/%m/%Y")}'
            }
            
        except Exception as e:
            return {'error': f'Error al crear apartado: {str(e)}'}
    
    @api.model
    def create_lot_hold_enhanced(self, quant_id=None, partner_id=None, project_id=None, 
                                architect_id=None, notas='', currency_code='USD', 
                                product_prices=None):
        """
        Crear un hold completo con toda la información (versión avanzada)
        
        Args:
            quant_id: int - ID del quant
            partner_id: int - ID del cliente
            project_id: int - ID del proyecto
            architect_id: int - ID del arquitecto
            notas: str - Notas adicionales
            currency_code: str - Código de divisa
            product_prices: dict - Precios de productos
            
        Returns:
            dict: Resultado de la operación
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        if not partner_id:
            return {'error': 'Debe seleccionar un cliente'}
        
        if not project_id:
            return {'error': 'Debe seleccionar un proyecto'}
        
        if not architect_id:
            return {'error': 'Debe seleccionar un arquitecto'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            # Verificar hold existente
            hold_existente = self.env['stock.lot.hold'].search([
                ('quant_id', '=', quant.id),
                ('estado', '=', 'activo')
            ], limit=1)
            
            if hold_existente:
                return {
                    'error': f'Este lote ya tiene una reserva activa para {hold_existente.partner_id.name}'
                }
            
            # Calcular fecha de expiración (5 días hábiles)
            from datetime import timedelta
            fecha_inicio = fields.Datetime.now()
            fecha_actual = fecha_inicio
            dias_agregados = 0
            
            while dias_agregados < 5:
                fecha_actual += timedelta(days=1)
                if fecha_actual.weekday() < 5:  # Lunes a viernes
                    dias_agregados += 1
            
            # Agregar información de precios a las notas
            notes_with_prices = notas or ''
            if product_prices:
                notes_with_prices += f'\n\n=== PRECIOS ({currency_code}) ===\n'
                for product_id_str, price in product_prices.items():
                    try:
                        product = self.env['product.product'].browse(int(product_id_str))
                        if product.exists():
                            notes_with_prices += f'• {product.display_name}: {price:.2f} {currency_code}/m²\n'
                    except Exception as e:
                        _logger.warning(f"Error agregando precio para producto {product_id_str}: {str(e)}")
            
            # Crear el hold
            hold = self.env['stock.lot.hold'].create({
                'lot_id': quant.lot_id.id,
                'quant_id': quant.id,
                'partner_id': partner_id,
                'user_id': self.env.user.id,
                'project_id': project_id,
                'arquitecto_id': architect_id,
                'fecha_inicio': fecha_inicio,
                'fecha_expiracion': fecha_actual,
                'notas': notes_with_prices,
            })
            
            partner = self.env['res.partner'].browse(partner_id)
            
            return {
                'success': True,
                'hold_id': hold.id,
                'message': f'Lote {quant.lot_id.name} apartado para {partner.name} hasta {hold.fecha_expiracion.strftime("%d/%m/%Y %H:%M")}'
            }
            
        except Exception as e:
            return {'error': f'Error al crear apartado: {str(e)}'}
    
    
    

    @api.model
    def create_holds_from_cart(self, partner_id=None, project_id=None, 
                            architect_id=None, selected_lots=None, 
                            notes=None, currency_code='USD', 
                            product_prices=None):
        """
        Crear holds múltiples desde el carrito con información de precios
        
        Args:
            partner_id: int - ID del cliente
            project_id: int - ID del proyecto
            architect_id: int - ID del arquitecto
            selected_lots: list - Lista de IDs de quants
            notes: str - Notas adicionales
            currency_code: str - Código de divisa (USD/MXN)
            product_prices: dict - Precios por producto
            
        Returns:
            dict: Resultado con éxitos y errores
        """
        if not partner_id or not selected_lots:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Parámetros inválidos: partner_id o selected_lots'}]
            }
        
        if not project_id:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Debe seleccionar un proyecto'}]
            }
        
        if not architect_id:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Debe seleccionar un arquitecto'}]
            }
        
        # Calcular fecha de expiración (5 días hábiles)
        from datetime import timedelta
        fecha_inicio = fields.Datetime.now()
        fecha_actual = fecha_inicio
        dias_agregados = 0
        
        while dias_agregados < 5:
            fecha_actual += timedelta(days=1)
            if fecha_actual.weekday() < 5:  # Lunes a viernes
                dias_agregados += 1
        
        fecha_expiracion = fecha_actual
        
        # Preparar notas con información de precios
        notes_with_prices = notes or ''
        if product_prices:
            notes_with_prices += f'\n\n=== PRECIOS ({currency_code}) ===\n'
            for product_id_str, price in product_prices.items():
                try:
                    product = self.env['product.product'].browse(int(product_id_str))
                    if product.exists():
                        notes_with_prices += f'• {product.display_name}: {price:.2f} {currency_code}/m²\n'
                except Exception as e:
                    _logger.warning(f"Error agregando precio para producto {product_id_str}: {str(e)}")
        
        # Crear holds
        holds_created = []
        errors = []
        
        for quant_id in selected_lots:
            try:
                quant = self.browse(quant_id)
                
                if not quant.exists():
                    errors.append({
                        'quant_id': quant_id,
                        'error': 'Quant no encontrado'
                    })
                    continue
                
                if not quant.lot_id:
                    errors.append({
                        'quant_id': quant_id,
                        'error': 'Quant sin lote asignado'
                    })
                    continue
                
                # Verificar si ya tiene hold
                if quant.x_tiene_hold:
                    errors.append({
                        'lot_name': quant.lot_id.name,
                        'error': f'Ya apartado para {quant.x_hold_para}'
                    })
                    continue
                
                # Crear el hold
                hold = self.env['stock.lot.hold'].create({
                    'lot_id': quant.lot_id.id,
                    'quant_id': quant.id,
                    'partner_id': partner_id,
                    'user_id': self.env.user.id,
                    'project_id': project_id,
                    'arquitecto_id': architect_id,
                    'fecha_inicio': fecha_inicio,
                    'fecha_expiracion': fecha_expiracion,
                    'notas': notes_with_prices,
                })
                
                holds_created.append({
                    'lot_name': quant.lot_id.name,
                    'hold_id': hold.id,
                    'expira': hold.fecha_expiracion.strftime('%d/%m/%Y %H:%M')
                })
                
            except Exception as e:
                errors.append({
                    'lot_name': quant.lot_id.name if quant.exists() and quant.lot_id else 'Desconocido',
                    'error': str(e)
                })
        
        # Limpiar carrito si hubo éxitos
        if holds_created:
            try:
                self.env['shopping.cart'].clear_cart()
            except Exception as e:
                _logger.warning(f"Error al limpiar carrito: {str(e)}")
        
        return {
            'success': len(holds_created),
            'errors': len(errors),
            'holds': holds_created,
            'failed': errors
        }

    # ==================== MÉTODOS DE BÚSQUEDA AUXILIARES ====================
    
    @api.model
    def search_partners(self, name=''):
        """
        Buscar partners (clientes)
        
        Args:
            name: str - Término de búsqueda
            
        Returns:
            list: Lista de partners encontrados
        """
        if not name or name.strip() == '':
            domain = [
                ('active', '=', True),
                '|', '|',
                ('customer_rank', '>', 0),
                ('supplier_rank', '>', 0),
                ('is_company', '=', True)
            ]
        else:
            search_term = name.strip()
            domain = [
                ('active', '=', True),
                '|', '|', '|', '|',
                ('name', 'ilike', search_term),
                ('ref', 'ilike', search_term),
                ('vat', 'ilike', search_term),
                ('email', 'ilike', search_term),
                ('phone', 'ilike', search_term)
            ]
        
        partners = self.env['res.partner'].search(domain, limit=50, order='name')
        
        result = []
        for partner in partners:
            display_parts = [partner.name]
            if partner.ref:
                display_parts.append(f"[{partner.ref}]")
            if partner.vat:
                display_parts.append(f"RFC: {partner.vat}")
            
            display_name = ' '.join(display_parts)
            
            result.append({
                'id': partner.id,
                'name': partner.name,
                'ref': partner.ref or '',
                'vat': partner.vat or '',
                'display_name': display_name
            })
        
        return result
    
    @api.model
    def get_projects(self, search_term=''):
        """Buscar proyectos de mármol"""
        domain = [('x_es_proyecto_marmol', '=', True)]
        
        if search_term:
            domain.append(('name', 'ilike', search_term))
        
        projects = self.env['project.project'].search(domain, limit=50, order='name')
        
        result = []
        for project in projects:
            result.append({
                'id': project.id,
                'name': project.name,
            })
        
        return result
    
    @api.model
    def get_architects(self, search_term=''):
        """Buscar arquitectos"""
        domain = [('x_es_arquitecto', '=', True)]
        
        if search_term:
            domain.append(('name', 'ilike', search_term))
        
        architects = self.env['res.partner'].search(domain, limit=50, order='name')
        
        result = []
        for architect in architects:
            display_parts = [architect.name]
            if architect.ref:
                display_parts.append(f"[{architect.ref}]")
            if architect.vat:
                display_parts.append(f"RFC: {architect.vat}")
            
            display_name = ' '.join(display_parts)
            
            result.append({
                'id': architect.id,
                'name': architect.name,
                'ref': architect.ref or '',
                'vat': architect.vat or '',
                'display_name': display_name
            })
        
        return result
    
    # ==================== MÉTODOS DE CREACIÓN AUXILIARES ====================
    
    @api.model
    def create_partner(self, name, vat='', ref=''):
        """Crear un nuevo cliente"""
        try:
            partner = self.env['res.partner'].create({
                'name': name,
                'vat': vat or False,
                'ref': ref or False,
                'customer_rank': 1,
                'company_type': 'company',
            })
            
            return {
                'success': True,
                'partner_id': partner.id,
                'partner': {
                    'id': partner.id,
                    'name': partner.name,
                    'ref': partner.ref or '',
                    'vat': partner.vat or '',
                    'display_name': partner.name
                }
            }
        except Exception as e:
            return {'error': str(e)}
    
    @api.model
    def create_project(self, name):
        """Crear un nuevo proyecto"""
        try:
            project = self.env['project.project'].create({
                'name': name,
                'x_es_proyecto_marmol': True,
            })
            
            return {
                'success': True,
                'project_id': project.id,
                'project': {
                    'id': project.id,
                    'name': project.name,
                }
            }
        except Exception as e:
            return {'error': str(e)}
    
    @api.model
    def create_architect(self, name, vat='', ref=''):
        """Crear un nuevo arquitecto"""
        try:
            architect = self.env['res.partner'].create({
                'name': name,
                'vat': vat or False,
                'ref': ref or False,
                'x_es_arquitecto': True,
                'company_type': 'person',
            })
            
            return {
                'success': True,
                'architect_id': architect.id,
                'architect': {
                    'id': architect.id,
                    'name': architect.name,
                    'ref': architect.ref or '',
                    'vat': architect.vat or '',
                    'display_name': architect.name
                }
            }
        except Exception as e:
            return {'error': str(e)}```

## ./models/utils/__init__.py
```py
# models/utils/__init__.py
# -*- coding: utf-8 -*-
from . import picking_cleaner
from . import dimension_fields
from . import photo_helpers
from . import business_days
from . import notification_builder
from . import image_processor
from . import metadata_fields
from . import hold_validator
from . import lot_dimension_sync
from . import plate_status_builder
from . import bulk_hold_creator```

## ./models/utils/bulk_hold_creator.py
```py
# models/utils/bulk_hold_creator.py
# -*- coding: utf-8 -*-
"""
Creador de holds masivos desde carrito
"""
from odoo import fields
from .business_days import BusinessDaysCalculator
import logging

_logger = logging.getLogger(__name__)


class BulkHoldCreator:
    """Creador de múltiples holds desde carrito de compras"""
    
    def __init__(self, env):
        self.env = env
    
    def create_holds_from_cart(self, partner_id, project_id, architect_id, 
                               selected_lots, notes=None, currency_code='USD', 
                               product_prices=None):
        """
        Crea múltiples holds con validaciones
        
        Args:
            partner_id: int - ID del cliente
            project_id: int - ID del proyecto
            architect_id: int - ID del arquitecto
            selected_lots: list - IDs de quants
            notes: str - Notas adicionales
            currency_code: str - Código de divisa
            product_prices: dict - Precios por producto
            
        Returns:
            dict: Resultado con éxitos y errores
        """
        # Validar parámetros
        validation_error = self._validate_parameters(
            partner_id, project_id, architect_id, selected_lots
        )
        if validation_error:
            return validation_error
        
        # Calcular fecha de expiración
        fecha_inicio = fields.Datetime.now()
        fecha_expiracion = BusinessDaysCalculator.get_expiration_date(
            fecha_inicio, 
            days=5
        )
        
        # Preparar notas con precios
        notes_with_prices = self._build_notes_with_prices(
            notes, currency_code, product_prices
        )
        
        # Crear holds
        holds_created, errors = self._create_holds(
            selected_lots,
            partner_id,
            project_id,
            architect_id,
            fecha_inicio,
            fecha_expiracion,
            notes_with_prices
        )
        
        # Limpiar carrito si hubo éxitos
        if holds_created:
            self._clear_cart()
        
        return {
            'success': len(holds_created),
            'errors': len(errors),
            'holds': holds_created,
            'failed': errors
        }
    
    def _validate_parameters(self, partner_id, project_id, architect_id, selected_lots):
        """Valida parámetros requeridos"""
        if not partner_id or not selected_lots:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Parámetros inválidos'}]
            }
        
        if not project_id:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Debe seleccionar un proyecto'}]
            }
        
        if not architect_id:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Debe seleccionar un arquitecto'}]
            }
        
        return None
    
    def _build_notes_with_prices(self, notes, currency_code, product_prices):
        """Construye notas con información de precios"""
        notes_with_prices = notes or ''
        
        if not product_prices:
            return notes_with_prices
        
        notes_with_prices += f'\n\n=== PRECIOS ({currency_code}) ===\n'
        
        for product_id_str, price in product_prices.items():
            try:
                product = self.env['product.product'].browse(int(product_id_str))
                if product.exists():
                    notes_with_prices += (
                        f'• {product.display_name}: '
                        f'{price:.2f} {currency_code}/m²\n'
                    )
            except Exception as e:
                _logger.warning(
                    "Error agregando precio para producto %s: %s",
                    product_id_str, str(e)
                )
        
        return notes_with_prices
    
    def _create_holds(self, selected_lots, partner_id, project_id, architect_id,
                     fecha_inicio, fecha_expiracion, notes):
        """Crea holds para cada lote seleccionado"""
        holds_created = []
        errors = []
        
        for quant_id in selected_lots:
            quant = self.env['stock.quant'].browse(quant_id)
            
            # Validar quant
            if not quant.exists() or not quant.lot_id:
                errors.append({
                    'quant_id': quant_id,
                    'error': 'Quant no válido o sin lote'
                })
                continue
            
            # Verificar hold existente
            if quant.x_tiene_hold:
                errors.append({
                    'lot_name': quant.lot_id.name,
                    'error': f'Ya apartado para {quant.x_hold_para}'
                })
                continue
            
            # Crear hold
            try:
                hold = self._create_single_hold(
                    quant, partner_id, project_id, architect_id,
                    fecha_inicio, fecha_expiracion, notes
                )
                
                holds_created.append({
                    'lot_name': quant.lot_id.name,
                    'hold_id': hold.id,
                    'expira': hold.fecha_expiracion.strftime('%d/%m/%Y %H:%M')
                })
            except Exception as e:
                errors.append({
                    'lot_name': quant.lot_id.name,
                    'error': str(e)
                })
        
        return holds_created, errors
    
    def _create_single_hold(self, quant, partner_id, project_id, architect_id,
                           fecha_inicio, fecha_expiracion, notes):
        """Crea un hold individual"""
        return self.env['stock.lot.hold'].create({
            'lot_id': quant.lot_id.id,
            'quant_id': quant.id,
            'partner_id': partner_id,
            'user_id': self.env.user.id,
            'project_id': project_id,
            'arquitecto_id': architect_id,
            'fecha_inicio': fecha_inicio,
            'fecha_expiracion': fecha_expiracion,
            'notas': notes,
        })
    
    def _clear_cart(self):
        """Limpia el carrito después de crear holds"""
        try:
            self.env['shopping.cart'].clear_cart()
        except Exception as e:
            _logger.warning("Error al limpiar carrito: %s", str(e))```

## ./models/utils/business_days.py
```py
# models/utils/business_days.py
# -*- coding: utf-8 -*-
"""
Utilidades para cálculo de días hábiles (lunes a viernes)
"""
from datetime import timedelta
from odoo import fields


class BusinessDaysCalculator:
    """Calculadora de días hábiles excluyendo sábados y domingos"""
    
    @staticmethod
    def is_business_day(date):
        """
        Verifica si una fecha es día hábil (lunes a viernes)
        
        Args:
            date: datetime object
            
        Returns:
            bool: True si es día hábil
        """
        return date.weekday() < 5
    
    @staticmethod
    def add_business_days(start_date, days):
        """
        Suma días hábiles a una fecha
        
        Args:
            start_date: datetime - Fecha de inicio
            days: int - Cantidad de días hábiles a sumar
            
        Returns:
            datetime: Fecha resultante
        """
        fecha_actual = start_date
        dias_agregados = 0
        
        while dias_agregados < days:
            fecha_actual += timedelta(days=1)
            if BusinessDaysCalculator.is_business_day(fecha_actual):
                dias_agregados += 1
        
        return fecha_actual
    
    @staticmethod
    def count_business_days(start_date, end_date):
        """
        Cuenta días hábiles entre dos fechas
        
        Args:
            start_date: datetime - Fecha de inicio
            end_date: datetime - Fecha de fin
            
        Returns:
            int: Cantidad de días hábiles
        """
        dias = 0
        fecha_actual = start_date
        
        while fecha_actual.date() < end_date.date():
            if BusinessDaysCalculator.is_business_day(fecha_actual):
                dias += 1
            fecha_actual += timedelta(days=1)
        
        return dias
    
    @staticmethod
    def get_expiration_date(start_date=None, days=5):
        """
        Calcula fecha de expiración sumando días hábiles
        
        Args:
            start_date: datetime - Fecha de inicio (default: ahora)
            days: int - Días hábiles a sumar (default: 5)
            
        Returns:
            datetime: Fecha de expiración
        """
        if start_date is None:
            start_date = fields.Datetime.now()
        
        return BusinessDaysCalculator.add_business_days(start_date, days)```

## ./models/utils/dimension_fields.py
```py
# models/utils/dimension_fields.py
# -*- coding: utf-8 -*-
"""
Definiciones reutilizables de campos de dimensiones para lotes
"""
from odoo import fields


class LotDimensionFields:
    """Colección de campos de dimensiones reutilizables"""
    
    @staticmethod
    def get_dimension_fields():
        """
        Retorna diccionario con campos de dimensiones físicas
        
        Returns:
            dict: Definiciones de campos
        """
        return {
            'x_grosor': fields.Float(
                string='Grosor (cm)',
                digits=(10, 2),
                help='Grosor del producto en centímetros'
            ),
            'x_alto': fields.Float(
                string='Alto (m)',
                digits=(10, 4),
                help='Alto del producto en metros'
            ),
            'x_ancho': fields.Float(
                string='Ancho (m)',
                digits=(10, 4),
                help='Ancho del producto en metros'
            ),
        }
    
    @staticmethod
    def get_classification_fields():
        """
        Retorna diccionario con campos de clasificación
        
        Returns:
            dict: Definiciones de campos
        """
        return {
            'x_tipo': fields.Selection(
                [('placa', 'Placa'), ('formato', 'Formato')],
                string='Tipo',
                help='Tipo de producto: Placa o Formato'
            ),
            'x_bloque': fields.Char(
                string='Bloque',
                help='Identificación del bloque de origen'
            ),
            'x_atado': fields.Char(
                string='Atado',
                help='Identificación del atado'
            ),
            'x_grupo': fields.Many2many(
                'stock.lot.group',
                string='Grupo',
                help='Etiquetas de grupo para clasificación'
            ),
        }
    
    @staticmethod
    def get_logistics_fields():
        """
        Retorna diccionario con campos logísticos
        
        Returns:
            dict: Definiciones de campos
        """
        return {
            'x_pedimento': fields.Char(
                string='Pedimento',
                help='Número de pedimento aduanal'
            ),
            'x_contenedor': fields.Char(
                string='Contenedor',
                help='Número de contenedor'
            ),
            'x_referencia_proveedor': fields.Char(
                string='Referencia Proveedor',
                help='Referencia del proveedor'
            ),
        }
    
    @staticmethod
    def get_all_fields():
        """
        Retorna todos los campos combinados
        
        Returns:
            dict: Todas las definiciones de campos
        """
        all_fields = {}
        all_fields.update(LotDimensionFields.get_dimension_fields())
        all_fields.update(LotDimensionFields.get_classification_fields())
        all_fields.update(LotDimensionFields.get_logistics_fields())
        return all_fields```

## ./models/utils/hold_validator.py
```py
# -*- coding: utf-8 -*-
"""
Validador centralizado para holds de lotes con soporte multi-compañía
"""
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class HoldValidator:
    """Validador de holds en lotes para entregas con soporte multi-compañía"""
    
    def __init__(self, env):
        self.env = env
    
    def get_customer_from_picking(self, move_line):
        """
        Obtiene el cliente del picking o sale order
        
        Args:
            move_line: stock.move.line record
            
        Returns:
            res.partner: Cliente o None
        """
        if not move_line.picking_id:
            return None
        
        # Intentar desde picking
        partner = move_line.picking_id.partner_id
        
        # Intentar desde sale order
        if move_line.move_id and move_line.move_id.sale_line_id:
            partner = move_line.move_id.sale_line_id.order_id.partner_id
        
        return partner
    
    def get_available_lots(self, product_id, location_id, customer_id, company_id=None):
        """
        Obtiene IDs de lotes disponibles para un cliente en una compañía específica
        
        Args:
            product_id: int - ID del producto
            location_id: int - ID de la ubicación
            customer_id: int - ID del cliente
            company_id: int - ID de la compañía (opcional, usa la actual por defecto)
            
        Returns:
            list: IDs de lotes disponibles
        """
        if company_id is None:
            company_id = self.env.company.id
        
        # Buscar quants de la compañía especificada
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product_id),
            ('location_id', '=', location_id),
            ('quantity', '>', 0),
            ('company_id', '=', company_id),
        ])
        
        available_lots = []
        
        for quant in quants:
            if not quant.lot_id:
                continue
            
            # Sin hold → disponible para todos
            if not quant.x_tiene_hold:
                available_lots.append(quant.lot_id.id)
                continue
            
            # Con hold → verificar compañía y cliente
            if quant.x_hold_activo_id:
                # Verificar que sea de la misma compañía
                if quant.x_hold_activo_id.company_id.id == company_id:
                    # Hold de la misma compañía → verificar cliente
                    hold_partner_id = quant.x_hold_activo_id.partner_id.id
                    if hold_partner_id == customer_id:
                        available_lots.append(quant.lot_id.id)
                else:
                    # Hold de otra compañía → lote disponible
                    available_lots.append(quant.lot_id.id)
                    _logger.debug(
                        "Lote %s disponible: hold es de otra compañía (Hold: %s, Buscado: %s)",
                        quant.lot_id.name,
                        quant.x_hold_activo_id.company_id.name,
                        self.env['res.company'].browse(company_id).name
                    )
        
        _logger.debug(
            "Lotes disponibles para producto=%s, ubicación=%s, cliente=%s, compañía=%s: %d lotes",
            product_id,
            location_id,
            customer_id,
            company_id,
            len(available_lots)
        )
        
        return available_lots
    
    def validate_lot_assignment(self, lot_id, location_id, customer_id, company_id=None):
        """
        Valida si un lote puede ser asignado a un cliente en una compañía específica
        
        Args:
            lot_id: int - ID del lote
            location_id: int - ID de la ubicación
            customer_id: int - ID del cliente
            company_id: int - ID de la compañía (opcional, usa la actual por defecto)
            
        Raises:
            ValidationError: Si el lote está reservado para otro cliente en la misma compañía
        """
        if company_id is None:
            company_id = self.env.company.id
        
        # Buscar quant con hold en la compañía especificada
        quant = self.env['stock.quant'].search([
            ('lot_id', '=', lot_id),
            ('location_id', '=', location_id),
            ('quantity', '>', 0),
            ('company_id', '=', company_id),
            ('x_tiene_hold', '=', True),
        ], limit=1)
        
        if not quant or not quant.x_hold_activo_id:
            return  # Sin hold, permitir
        
        # Verificar que el hold sea de la misma compañía
        if quant.x_hold_activo_id.company_id.id != company_id:
            _logger.debug(
                "Hold de lote %s es de otra compañía, permitiendo asignación",
                quant.lot_id.name
            )
            return  # Hold de otra compañía no aplica
        
        # Hold de la misma compañía → verificar cliente
        hold_partner = quant.x_hold_activo_id.partner_id
        
        if hold_partner.id != customer_id:
            # 🔑 Cargar objetos completos ANTES de construir el mensaje
            lot = self.env['stock.lot'].browse(lot_id)
            customer = self.env['res.partner'].browse(customer_id)
            company = self.env['res.company'].browse(company_id)
            
            error_msg = (
                f"🔒 NO PUEDE USAR ESTE LOTE\n\n"
                f"El lote '{lot.name}' está RESERVADO para:\n"
                f"👤 {hold_partner.name}\n"
                f"📅 Hasta: {quant.x_hold_expira.strftime('%d/%m/%Y %H:%M')}\n"
                f"⏱️ Días restantes: {quant.x_hold_dias_restantes}\n"
                f"🏢 Compañía: {company.name}\n\n"
                f"❌ Esta entrega es para '{customer.name}'\n\n"
                f"Por favor, seleccione un lote disponible."
            )
            
            _logger.warning(
                "Validación de hold fallida: Lote=%s, Hold para=%s, "
                "Intentando asignar a=%s, Compañía=%s",
                lot.name,
                hold_partner.name,
                customer.name,
                company.name
            )
            
            raise ValidationError(error_msg)
        
        # Validación exitosa - obtener nombre del cliente para log
        customer = self.env['res.partner'].browse(customer_id)
        _logger.debug(
            "Validación de hold exitosa: Lote %s para cliente %s en compañía %s",
            quant.lot_id.name,
            customer.name,
            company_id
        )```

## ./models/utils/image_processor.py
```py
# models/utils/image_processor.py
# -*- coding: utf-8 -*-
"""
Utilidades para procesamiento de imágenes
"""
from odoo import fields


class ImageProcessor:
    """Procesador de imágenes y miniaturas"""
    
    @staticmethod
    def get_image_fields(model_name, foreign_key_field):
        """
        Retorna definiciones de campos estándar para imágenes
        
        Args:
            model_name: str - Nombre del modelo relacionado (ej: 'stock.lot')
            foreign_key_field: str - Campo de relación (ej: 'lot_id')
            
        Returns:
            dict: Definiciones de campos de imagen
        """
        return {
            'name': fields.Char(
                string='Nombre',
                required=True,
                default='Fotografía'
            ),
            'sequence': fields.Integer(
                string='Secuencia',
                default=10,
                help='Orden de visualización de las fotografías'
            ),
            foreign_key_field: fields.Many2one(
                model_name,
                string='Registro',
                required=True,
                ondelete='cascade',
                index=True
            ),
            'image': fields.Binary(
                string='Imagen',
                required=True,
                attachment=True
            ),
            'image_small': fields.Binary(
                string='Miniatura',
                compute='_compute_image_small',
                store=True
            ),
            'fecha_captura': fields.Datetime(
                string='Fecha de Captura',
                default=fields.Datetime.now,
                readonly=True
            ),
            'notas': fields.Text(
                string='Notas'
            ),
        }
    
    @staticmethod
    def compute_thumbnail(records):
        """
        Genera miniatura de la imagen principal
        Odoo maneja automáticamente el redimensionamiento
        
        Args:
            records: recordset con campos 'image' e 'image_small'
        """
        for record in records:
            record.image_small = record.image if record.image else False
    
    @staticmethod
    def get_default_order():
        """
        Retorna el orden por defecto para modelos de imágenes
        
        Returns:
            str: String de ordenamiento
        """
        return 'sequence, id'```

## ./models/utils/lot_dimension_sync.py
```py
# models/utils/lot_dimension_sync.py
# -*- coding: utf-8 -*-
"""
Sincronización de dimensiones temporales con lotes
"""


class LotDimensionSync:
    """Sincronizador de campos temporales de dimensiones al lote"""
    
    # Mapeo de campos temporales a campos del lote
    DIMENSION_MAPPING = {
        'x_grosor_temp': 'x_grosor',
        'x_alto_temp': 'x_alto',
        'x_ancho_temp': 'x_ancho',
        'x_bloque_temp': 'x_bloque',
        'x_atado_temp': 'x_atado',
        'x_tipo_temp': 'x_tipo',
        'x_pedimento_temp': 'x_pedimento',
        'x_contenedor_temp': 'x_contenedor',
        'x_referencia_proveedor_temp': 'x_referencia_proveedor',
    }
    
    @staticmethod
    def load_dimensions_from_lot(move_line):
        """
        Carga dimensiones del lote a campos temporales
        
        Args:
            move_line: stock.move.line record
        """
        if not move_line.lot_id:
            return
        
        lot = move_line.lot_id
        move_line.x_grosor_temp = lot.x_grosor
        move_line.x_alto_temp = lot.x_alto
        move_line.x_ancho_temp = lot.x_ancho
        move_line.x_bloque_temp = lot.x_bloque
        move_line.x_atado_temp = lot.x_atado
        move_line.x_tipo_temp = lot.x_tipo
    
    @staticmethod
    def sync_dimensions_to_lot(move_line):
        """
        Sincroniza dimensiones temporales al lote
        
        Args:
            move_line: stock.move.line record
            
        Returns:
            dict: Valores a escribir en el lote
        """
        lot_vals = {}
        
        for temp_field, lot_field in LotDimensionSync.DIMENSION_MAPPING.items():
            value = getattr(move_line, temp_field, None)
            if value:
                lot_vals[lot_field] = value
        
        # Campo many2many requiere formato especial
        if move_line.x_grupo_temp:
            lot_vals['x_grupo'] = [(6, 0, move_line.x_grupo_temp.ids)]
        
        return lot_vals
    
    @staticmethod
    def calculate_area(alto, ancho):
        """
        Calcula área en m²
        
        Args:
            alto: float - Alto en metros
            ancho: float - Ancho en metros
            
        Returns:
            float: Área en m²
        """
        if alto and ancho:
            return alto * ancho
        return 0.0
    
    @staticmethod
    def get_available_quantity(env, lot_id, location_id, product_id, move_qty=None):
        """
        Obtiene cantidad disponible de un lote
        
        Args:
            env: Environment
            lot_id: int - ID del lote
            location_id: int - ID de ubicación
            product_id: int - ID del producto
            move_qty: float - Cantidad solicitada en el move
            
        Returns:
            float: Cantidad disponible
        """
        quant = env['stock.quant'].search([
            ('lot_id', '=', lot_id),
            ('location_id', '=', location_id),
            ('product_id', '=', product_id)
        ], limit=1)
        
        if not quant or quant.available_quantity <= 0:
            return 0.0
        
        available = quant.available_quantity
        
        if move_qty:
            return min(available, move_qty)
        
        return available```

## ./models/utils/metadata_fields.py
```py
# models/utils/metadata_fields.py
# -*- coding: utf-8 -*-
"""
Definiciones de campos metadata reutilizables
"""
from odoo import fields


class MetadataFields:
    """Colección de campos metadata comunes"""
    
    @staticmethod
    def get_name_field(default_name='Registro'):
        """
        Campo nombre estándar
        
        Args:
            default_name: str - Nombre por defecto
            
        Returns:
            fields.Char: Definición del campo
        """
        return fields.Char(
            string='Nombre',
            required=True,
            default=default_name
        )
    
    @staticmethod
    def get_sequence_field(default=10):
        """
        Campo secuencia estándar
        
        Args:
            default: int - Valor por defecto
            
        Returns:
            fields.Integer: Definición del campo
        """
        return fields.Integer(
            string='Secuencia',
            default=default,
            help='Orden de visualización'
        )
    
    @staticmethod
    def get_notes_field():
        """Campo notas estándar"""
        return fields.Text(string='Notas')
    
    @staticmethod
    def get_capture_date_field():
        """Campo fecha de captura con timestamp automático"""
        return fields.Datetime(
            string='Fecha de Captura',
            default=fields.Datetime.now,
            readonly=True
        )
    
    @staticmethod
    def get_active_field():
        """Campo activo estándar"""
        return fields.Boolean(
            string='Activo',
            default=True
        )```

## ./models/utils/notification_builder.py
```py
# models/utils/notification_builder.py
# -*- coding: utf-8 -*-
"""
Constructor de notificaciones de cliente
"""


class NotificationBuilder:
    """Constructor de notificaciones para acciones de Odoo"""
    
    @staticmethod
    def build_success(title, message, sticky=False):
        """
        Construye notificación de éxito
        
        Args:
            title: str - Título de la notificación
            message: str - Mensaje de la notificación
            sticky: bool - Si la notificación permanece en pantalla
            
        Returns:
            dict: Acción de notificación
        """
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'success',
                'sticky': sticky,
            }
        }
    
    @staticmethod
    def build_warning(title, message, sticky=False):
        """Construye notificación de advertencia"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'warning',
                'sticky': sticky,
            }
        }
    
    @staticmethod
    def build_error(title, message, sticky=True):
        """Construye notificación de error"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'danger',
                'sticky': sticky,
            }
        }
    
    @staticmethod
    def build_info(title, message, sticky=False):
        """Construye notificación informativa"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'info',
                'sticky': sticky,
            }
        }```

## ./models/utils/photo_helpers.py
```py
# models/utils/photo_helpers.py
# -*- coding: utf-8 -*-
"""
Utilidades para manejo de fotografías en lotes
"""
from odoo import fields


class PhotoHelper:
    """Helper para operaciones con fotografías de lotes"""
    
    @staticmethod
    def get_photo_fields():
        """
        Retorna definiciones de campos relacionados con fotografías
        
        Returns:
            dict: Definiciones de campos de fotografías
        """
        return {
            'x_fotografia_ids': fields.One2many(
                'stock.lot.image',
                'lot_id',
                string='Fotografías',
                help='Fotografías del producto/lote'
            ),
            'x_fotografia_principal': fields.Binary(
                string='Foto Principal',
                compute='_compute_fotografia_principal',
                store=False
            ),
            'x_tiene_fotografias': fields.Boolean(
                string='Tiene Fotos',
                compute='_compute_tiene_fotografias',
                store=True
            ),
            'x_cantidad_fotos': fields.Integer(
                string='# Fotos',
                compute='_compute_cantidad_fotos',
                store=True
            ),
        }
    
    @staticmethod
    def compute_main_photo(records):
        """
        Calcula la foto principal (primera foto disponible)
        
        Args:
            records: recordset con campo x_fotografia_ids
        """
        for record in records:
            if record.x_fotografia_ids:
                record.x_fotografia_principal = record.x_fotografia_ids[0].image
            else:
                record.x_fotografia_principal = False
    
    @staticmethod
    def compute_has_photos(records):
        """
        Calcula si el registro tiene fotografías
        
        Args:
            records: recordset con campo x_fotografia_ids
        """
        for record in records:
            record.x_tiene_fotografias = bool(record.x_fotografia_ids)
    
    @staticmethod
    def compute_photo_count(records):
        """
        Calcula cantidad de fotografías
        
        Args:
            records: recordset con campo x_fotografia_ids
        """
        for record in records:
            record.x_cantidad_fotos = len(record.x_fotografia_ids)
    
    @staticmethod
    def build_photo_gallery_action(lot_id, lot_name):
        """
        Construye acción para abrir galería de fotos
        
        Args:
            lot_id: ID del lote
            lot_name: Nombre del lote
            
        Returns:
            dict: Definición de acción de ventana
        """
        return {
            'name': f'Fotografías de {lot_name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'kanban,form',
            'views': [
                (False, 'kanban'),
                (False, 'form')
            ],
            'domain': [('lot_id', '=', lot_id)],
            'context': {
                'default_lot_id': lot_id,
                'create': True,
            },
            'target': 'current',
        }```

## ./models/utils/picking_cleaner.py
```py
# models/utils/picking_cleaner.py
# -*- coding: utf-8 -*-
"""
Utilidades para limpieza de lotes automáticos en pickings
"""
import logging

_logger = logging.getLogger(__name__)

class PickingLotCleaner:
    """Maneja la limpieza de lotes asignados automáticamente en pickings"""
    
    def __init__(self, env):
        self.env = env
        self._move_line_model = env['stock.move.line']
        self._move_model = env['stock.move']
        self._picking_model = env['stock.picking']
    
    def clear_pickings_lots(self, pickings):
        """
        Elimina lotes automáticos de múltiples pickings
        
        Args:
            pickings: recordset de stock.picking
        """
        if not pickings:
            return
        
        _logger.info("Limpiando lotes automáticos de %d pickings", len(pickings))
        
        for picking in pickings:
            self._clear_single_picking(picking)
    
    def _clear_single_picking(self, picking):
        """Limpia un picking individual"""
        move_lines = self._get_clearable_move_lines(picking)
        
        if not move_lines:
            return
        
        if self._delete_move_lines(move_lines, picking.name):
            self._reset_picking_state(picking)
            self._reset_moves_state(picking)
            self._invalidate_cache()
    
    def _get_clearable_move_lines(self, picking):
        """Obtiene move_lines que pueden ser eliminadas"""
        return self._move_line_model.search([
            ('picking_id', '=', picking.id),
            ('state', 'not in', ['done', 'cancel'])
        ])
    
    def _delete_move_lines(self, move_lines, picking_name):
        """
        Elimina move_lines con manejo de errores
        
        Returns:
            bool: True si se eliminaron exitosamente
        """
        try:
            move_lines.unlink()
            _logger.info("Eliminadas %d move_lines del picking %s", 
                        len(move_lines), picking_name)
            return True
        except Exception as e:
            _logger.error("Error eliminando move_lines del picking %s: %s", 
                         picking_name, str(e))
            return False
    
    def _reset_picking_state(self, picking):
        """Resetea el estado del picking de 'assigned' a 'confirmed'"""
        if picking.state != 'assigned':
            return
        
        try:
            picking.write({'state': 'confirmed'})
        except Exception as e:
            _logger.warning("No se pudo resetear estado del picking %s: %s", 
                          picking.name, str(e))
    
    def _reset_moves_state(self, picking):
        """Resetea el estado de los moves de 'assigned' a 'confirmed'"""
        moves_to_reset = picking.move_ids.filtered(lambda m: m.state == 'assigned')
        
        if not moves_to_reset:
            return
        
        try:
            moves_to_reset.write({'state': 'confirmed'})
        except Exception as e:
            _logger.warning("Error reseteando moves del picking %s: %s", 
                          picking.name, str(e))
    
    def _invalidate_cache(self):
        """Invalida caché de modelos de stock"""
        self._move_line_model.invalidate_model()
        self._move_model.invalidate_model()
        self._picking_model.invalidate_model()```

## ./models/utils/plate_status_builder.py
```py
# models/utils/plate_status_builder.py
# -*- coding: utf-8 -*-
"""
Constructor de estados visuales para placas
"""
import json


class PlateStatusBuilder:
    """Constructor de estados JSON para widget de visualización"""
    
    @staticmethod
    def build_hold_status(hold_para, dias_restantes):
        """
        Construye estado de hold manual
        
        Args:
            hold_para: str - Nombre del cliente
            dias_restantes: int - Días hábiles restantes
            
        Returns:
            dict: Estado de hold
        """
        dias_texto = (
            f'{dias_restantes} días hábiles' 
            if dias_restantes != 1 
            else '1 día hábil'
        )
        
        css_class = 'text-warning' if dias_restantes <= 2 else 'text-info'
        
        return {
            'type': 'hold',
            'icon': '🔒',
            'label': f'HOLD para {hold_para}',
            'detail': f'Expira en {dias_texto}',
            'class': css_class
        }
    
    @staticmethod
    def build_delivery_status(picking_name):
        """
        Construye estado de orden de entrega
        
        Args:
            picking_name: str - Nombre del picking
            
        Returns:
            dict: Estado de entrega
        """
        return {
            'type': 'delivery',
            'icon': '📦',
            'label': 'En Orden de Entrega',
            'detail': f'Doc: {picking_name}',
            'class': 'text-primary'
        }
    
    @staticmethod
    def build_details_status(detalles_placa):
        """
        Construye estado de detalles especiales
        
        Args:
            detalles_placa: str - Detalles de la placa
            
        Returns:
            dict: Estado de detalles
        """
        detalles_cortos = (
            detalles_placa[:30] + '...' 
            if len(detalles_placa) > 30 
            else detalles_placa
        )
        
        return {
            'type': 'details',
            'icon': '⚠️',
            'label': 'Detalles Especiales',
            'detail': detalles_cortos,
            'class': 'text-danger'
        }
    
    @staticmethod
    def to_json(estados):
        """
        Convierte lista de estados a JSON
        
        Args:
            estados: list - Lista de estados
            
        Returns:
            str or False: JSON string o False si vacío
        """
        return json.dumps(estados) if estados else False```

## ./reports/stock_lot_hold_order_report.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Definición del reporte -->
    <record id="action_report_stock_lot_hold_order" model="ir.actions.report">
        <field name="name">Orden de Reserva</field>
        <field name="model">stock.lot.hold.order</field>
        <field name="report_type">qweb-pdf</field>
        <field name="report_name">stock_lot_dimensions.report_stock_lot_hold_order_document</field>
        <field name="report_file">stock_lot_dimensions.report_stock_lot_hold_order_document</field>
        <field name="print_report_name">'Reserva - %s' % (object.name)</field>
        <field name="binding_model_id" ref="model_stock_lot_hold_order"/>
        <field name="binding_type">report</field>
    </record>

    <!-- Template del reporte -->
    <template id="report_stock_lot_hold_order_document">
        <t t-call="web.html_container">
            <t t-foreach="docs" t-as="o">
                <t t-call="web.external_layout">
                    <div class="page">
                        <!-- Encabezado -->
                        <div class="row mt-4 mb-2">
                            <div class="col-6">
                                <h2>
                                    <span>Orden de Reserva</span>
                                </h2>
                            </div>
                            <div class="col-6 text-end">
                                <h3>
                                    <span t-field="o.name"/>
                                </h3>
                            </div>
                        </div>

                        <!-- Información General -->
                        <div class="row mb-4">
                            <div class="col-6">
                                <strong>Cliente:</strong><br/>
                                <span t-field="o.partner_id.name"/><br/>
                                <span t-if="o.partner_id.vat">
                                    RFC: <span t-field="o.partner_id.vat"/><br/>
                                </span>
                                <span t-if="o.partner_id.street">
                                    <span t-field="o.partner_id.street"/><br/>
                                </span>
                                <span t-if="o.partner_id.city">
                                    <span t-field="o.partner_id.city"/>,
                                </span>
                                <span t-if="o.partner_id.state_id">
                                    <span t-field="o.partner_id.state_id.name"/>
                                </span>
                                <span t-if="o.partner_id.zip">
                                    <span t-field="o.partner_id.zip"/>
                                </span>
                            </div>
                            <div class="col-6">
                                <strong>Vendedor:</strong><br/>
                                <span t-field="o.user_id.name"/><br/>
                                <t t-if="o.user_id.phone">
                                    Tel: <span t-field="o.user_id.phone"/><br/>
                                </t>
                                <t t-if="o.user_id.email">
                                    Email: <span t-field="o.user_id.email"/><br/>
                                </t>
                            </div>
                        </div>

                        <div class="row mb-4">
                            <div class="col-6">
                                <t t-if="o.project_id">
                                    <strong>Proyecto:</strong><br/>
                                    <span t-field="o.project_id.name"/><br/>
                                </t>
                                <t t-if="o.arquitecto_id">
                                    <strong>Arquitecto:</strong><br/>
                                    <span t-field="o.arquitecto_id.name"/><br/>
                                    <t t-if="o.arquitecto_id.phone">
                                        Tel: <span t-field="o.arquitecto_id.phone"/><br/>
                                    </t>
                                </t>
                            </div>
                            <div class="col-6">
                                <strong>Fecha Orden:</strong><br/>
                                <span t-field="o.fecha_orden" t-options='{"widget": "datetime", "format": "dd/MM/yyyy HH:mm"}'/><br/>
                                <strong>Válida hasta:</strong><br/>
                                <span t-field="o.fecha_expiracion" t-options='{"widget": "datetime", "format": "dd/MM/yyyy HH:mm"}'/><br/>
                                <t t-if="o.state == 'confirmed'">
                                    <strong>Días restantes:</strong> 
                                    <span t-field="o.dias_restantes"/> días hábiles<br/>
                                </t>
                                <strong>Estado:</strong>
                                <t t-if="o.state == 'draft'">
                                    <span class="badge bg-secondary">Borrador</span>
                                </t>
                                <t t-if="o.state == 'confirmed'">
                                    <span class="badge bg-success">Confirmada</span>
                                </t>
                                <t t-if="o.state == 'done'">
                                    <span class="badge bg-info">Finalizada</span>
                                </t>
                                <t t-if="o.state == 'cancel'">
                                    <span class="badge bg-danger">Cancelada</span>
                                </t>
                            </div>
                        </div>

                        <!-- Resumen -->
                        <div class="row mb-4">
                            <div class="col-12">
                                <div class="alert alert-info">
                                    <div class="row">
                                        <div class="col-6">
                                            <strong>Total de Placas Reservadas:</strong> <span t-field="o.total_placas"/>
                                        </div>
                                        <div class="col-6">
                                            <strong>Total m²:</strong> <span t-field="o.total_m2"/> m²
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Tabla de Placas -->
                        <h4 class="mt-4 mb-3">Detalle de Placas Reservadas</h4>
                        
                        <table class="table table-sm table-bordered">
                            <thead style="background-color: #f8f9fa;">
                                <tr>
                                    <th class="text-center" style="width: 5%;">#</th>
                                    <th style="width: 15%;">Lote/Serie</th>
                                    <th style="width: 25%;">Producto</th>
                                    <th class="text-center" style="width: 8%;">Grosor<br/>(cm)</th>
                                    <th class="text-center" style="width: 8%;">Alto<br/>(m)</th>
                                    <th class="text-center" style="width: 8%;">Ancho<br/>(m)</th>
                                    <th class="text-right" style="width: 8%;">m²</th>
                                    <th class="text-center" style="width: 8%;">Tipo</th>
                                    <th style="width: 15%;">Bloque/Atado</th>
                                </tr>
                            </thead>
                            <tbody>
                                <t t-set="sequence" t-value="1"/>
                                <tr t-foreach="o.hold_line_ids" t-as="line">
                                    <td class="text-center">
                                        <span t-esc="sequence"/>
                                        <t t-set="sequence" t-value="sequence + 1"/>
                                    </td>
                                    <td>
                                        <strong t-field="line.lot_id.name"/>
                                    </td>
                                    <td>
                                        <span t-field="line.product_id.display_name"/>
                                    </td>
                                    <td class="text-center">
                                        <span t-field="line.x_grosor" t-options='{"precision": 2}'/>
                                    </td>
                                    <td class="text-center">
                                        <span t-field="line.x_alto" t-options='{"precision": 4}'/>
                                    </td>
                                    <td class="text-center">
                                        <span t-field="line.x_ancho" t-options='{"precision": 4}'/>
                                    </td>
                                    <td class="text-right">
                                        <strong>
                                            <span t-field="line.cantidad_m2" t-options='{"precision": 2}'/>
                                        </strong>
                                    </td>
                                    <td class="text-center">
                                        <t t-if="line.x_tipo == 'placa'">
                                            <span class="badge bg-primary">Placa</span>
                                        </t>
                                        <t t-if="line.x_tipo == 'formato'">
                                            <span class="badge bg-secondary">Formato</span>
                                        </t>
                                    </td>
                                    <td>
                                        <t t-if="line.x_bloque">
                                            <small>Bloque: <span t-field="line.x_bloque"/></small><br/>
                                        </t>
                                        <t t-if="line.lot_id.x_atado">
                                            <small>Atado: <span t-field="line.lot_id.x_atado"/></small>
                                        </t>
                                    </td>
                                </tr>
                            </tbody>
                            <tfoot style="background-color: #e9ecef; font-weight: bold;">
                                <tr>
                                    <td colspan="6" class="text-right">TOTALES:</td>
                                    <td class="text-right">
                                        <span t-field="o.total_m2" t-options='{"precision": 2}'/> m²
                                    </td>
                                    <td class="text-center">
                                        <span t-field="o.total_placas"/> pzas
                                    </td>
                                    <td></td>
                                </tr>
                            </tfoot>
                        </table>

                        <!-- Detalles Adicionales por Placa -->
                        <t t-if="any(line.lot_id.x_pedimento or line.lot_id.x_contenedor or line.lot_id.x_referencia_proveedor or line.lot_id.x_detalles_placa for line in o.hold_line_ids)">
                            <div class="page-break"/>
                            <h4 class="mt-4 mb-3">Información Adicional por Placa</h4>
                            
                            <t t-foreach="o.hold_line_ids" t-as="line">
                                <t t-if="line.lot_id.x_pedimento or line.lot_id.x_contenedor or line.lot_id.x_referencia_proveedor or line.lot_id.x_detalles_placa">
                                    <div class="card mb-3" style="border: 1px solid #dee2e6;">
                                        <div class="card-header" style="background-color: #f8f9fa;">
                                            <strong>Lote: <span t-field="line.lot_id.name"/></strong>
                                            - <span t-field="line.product_id.display_name"/>
                                        </div>
                                        <div class="card-body">
                                            <div class="row">
                                                <t t-if="line.lot_id.x_pedimento">
                                                    <div class="col-4">
                                                        <strong>Pedimento:</strong><br/>
                                                        <span t-field="line.lot_id.x_pedimento"/>
                                                    </div>
                                                </t>
                                                <t t-if="line.lot_id.x_contenedor">
                                                    <div class="col-4">
                                                        <strong>Contenedor:</strong><br/>
                                                        <span t-field="line.lot_id.x_contenedor"/>
                                                    </div>
                                                </t>
                                                <t t-if="line.lot_id.x_referencia_proveedor">
                                                    <div class="col-4">
                                                        <strong>Ref. Proveedor:</strong><br/>
                                                        <span t-field="line.lot_id.x_referencia_proveedor"/>
                                                    </div>
                                                </t>
                                            </div>
                                            <t t-if="line.lot_id.x_detalles_placa">
                                                <div class="row mt-2">
                                                    <div class="col-12">
                                                        <strong>Detalles Especiales:</strong><br/>
                                                        <div class="alert alert-warning mb-0">
                                                            <span t-field="line.lot_id.x_detalles_placa"/>
                                                        </div>
                                                    </div>
                                                </div>
                                            </t>
                                        </div>
                                    </div>
                                </t>
                            </t>
                        </t>

                        <!-- Notas de la Orden -->
                        <t t-if="o.notas">
                            <div class="row mt-4">
                                <div class="col-12">
                                    <h5>Notas de la Reserva:</h5>
                                    <div class="alert alert-light">
                                        <span t-field="o.notas"/>
                                    </div>
                                </div>
                            </div>
                        </t>

                        <!-- Términos y Condiciones -->
                        <div class="row mt-5">
                            <div class="col-12">
                                <div style="border-top: 1px solid #dee2e6; padding-top: 10px;">
                                    <h6>Términos y Condiciones de la Reserva:</h6>
                                    <ul style="font-size: 10px;">
                                        <li>Las placas reservadas permanecerán apartadas hasta la fecha de expiración indicada.</li>
                                        <li>Esta reserva puede renovarse por períodos adicionales de 5 días hábiles.</li>
                                        <li>Después de la fecha de expiración, las placas quedarán disponibles automáticamente.</li>
                                        <li>Las dimensiones y características indicadas son aproximadas y pueden variar ligeramente.</li>
                                        <li>Se recomienda inspección física antes de la entrega final.</li>
                                    </ul>
                                </div>
                            </div>
                        </div>

                        <!-- Firmas -->
                        <div class="row mt-5">
                            <div class="col-6 text-center">
                                <div style="border-top: 1px solid black; width: 70%; margin: 0 auto; padding-top: 5px;">
                                    <strong>Vendedor</strong><br/>
                                    <span t-field="o.user_id.name"/>
                                </div>
                            </div>
                            <div class="col-6 text-center">
                                <div style="border-top: 1px solid black; width: 70%; margin: 0 auto; padding-top: 5px;">
                                    <strong>Cliente</strong><br/>
                                    <span t-field="o.partner_id.name"/>
                                </div>
                            </div>
                        </div>

                        <!-- Pie de página con información de impresión -->
                        <div class="row mt-3">
                            <div class="col-12 text-center" style="font-size: 9px; color: #6c757d;">
                                <p>
                                    Documento generado el <span t-esc="context_timestamp(datetime.datetime.now()).strftime('%d/%m/%Y %H:%M')"/>
                                    por <span t-esc="user.name"/>
                                </p>
                            </div>
                        </div>
                    </div>
                </t>
            </t>
        </t>
    </template>

    <!-- Estilos CSS adicionales para el reporte -->
    <template id="report_stock_lot_hold_order_styles">
        <style type="text/css">
            .page-break {
                page-break-before: always;
            }
            
            @media print {
                .table-bordered th,
                .table-bordered td {
                    border: 1px solid #dee2e6 !important;
                }
            }
            
            .card {
                box-shadow: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.075);
            }
            
            .badge {
                padding: 0.25em 0.6em;
                font-size: 85%;
                font-weight: 700;
            }
            
            .bg-primary {
                background-color: #007bff !important;
                color: white;
            }
            
            .bg-secondary {
                background-color: #6c757d !important;
                color: white;
            }
            
            .bg-success {
                background-color: #28a745 !important;
                color: white;
            }
            
            .bg-info {
                background-color: #17a2b8 !important;
                color: white;
            }
            
            .bg-danger {
                background-color: #dc3545 !important;
                color: white;
            }
        </style>
    </template>
</odoo>```

## ./security/stock_lot_hold_security.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">
        <!-- Regla multi-compañía para stock.lot.hold -->
        <record id="stock_lot_hold_comp_rule" model="ir.rule">
            <field name="name">Stock Lot Hold: multi-company</field>
            <field name="model_id" ref="model_stock_lot_hold"/>
            <field name="domain_force">[('company_id', 'in', company_ids)]</field>
            <field name="global" eval="True"/>
        </record>
    </data>
</odoo>```

## ./static/src/js/image_gallery_widget.js
```js
/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ImageGalleryWidget extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            images: [],
            currentIndex: 0,
            showModal: false,
        });
        this.loadImages();
    }

    async loadImages() {
        if (this.props.value) {
            const lotId = this.props.value;
            const images = await this.orm.searchRead(
                "stock.lot.image",
                [["lot_id", "=", lotId]],
                ["id", "name", "image", "sequence"],
                { order: "sequence, id" }
            );
            this.state.images = images;
        }
    }

    openGallery(index) {
        this.state.currentIndex = index;
        this.state.showModal = true;
    }

    closeGallery() {
        this.state.showModal = false;
    }

    nextImage() {
        if (this.state.currentIndex < this.state.images.length - 1) {
            this.state.currentIndex++;
        }
    }

    prevImage() {
        if (this.state.currentIndex > 0) {
            this.state.currentIndex--;
        }
    }

    getImageUrl(imageId) {
        return `/web/image/stock.lot.image/${imageId}/image`;
    }
}

ImageGalleryWidget.template = "stock_lot_dimensions.ImageGalleryWidget";

registry.category("fields").add("image_gallery", {
    component: ImageGalleryWidget,
});
```

## ./static/src/js/image_preview_widget.js
```js
/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ImagePreviewWidget extends Component {
    setup() {
        this.state = useState({
            showModal: false,
        });
    }

    get imageUrl() {
        if (!this.props.value) {
            return null;
        }
        // El valor viene como base64, lo convertimos a data URL
        return `data:image/png;base64,${this.props.value}`;
    }

    openPreview(ev) {
        // Prevenir que se abra el registro
        ev.stopPropagation();
        ev.preventDefault();
        
        if (this.props.value) {
            this.state.showModal = true;
        }
    }

    closePreview() {
        this.state.showModal = false;
    }
}

ImagePreviewWidget.template = "stock_lot_dimensions.ImagePreviewWidget";

registry.category("fields").add("image_preview_clickable", {
    component: ImagePreviewWidget,
});```

## ./static/src/js/status_icons_widget.js
```js
/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class StatusIconsWidget extends Component {
    static template = "stock_lot_dimensions.StatusIconsWidget";
    static supportedTypes = ["char"];

    setup() {
        this.notification = useService("notification");
    }

    get estados() {
        const data = this.props.record.data;
        return {
            reservado: data.x_esta_reservado || false,
            entrega: data.x_en_orden_entrega || false,
            detalles: data.x_tiene_detalles || false,
            textoDetalles: data.x_detalles_placa || 'Sin detalles'
        };
    }

    mostrarDetalles(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        this.notification.add(this.estados.textoDetalles, {
            title: "Detalles de la Placa",
            type: "info",
        });
    }
}

registry.category("fields").add("status_icons", {
    component: StatusIconsWidget,
});```

## ./static/src/xml/image_gallery.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="stock_lot_dimensions.ImageGalleryWidget" owl="1">
        <div class="image-gallery-container">
            <div class="image-gallery-thumbnails">
                <t t-foreach="state.images" t-as="image" t-key="image.id">
                    <img 
                        t-att-src="getImageUrl(image.id)" 
                        t-att-alt="image.name"
                        class="image-gallery-thumbnail"
                        t-on-click="() => openGallery(image_index)"
                    />
                </t>
            </div>
            
            <t t-if="state.showModal">
                <div class="image-gallery-modal" t-on-click="closeGallery">
                    <div class="image-gallery-content" t-on-click.stop="">
                        <button class="image-gallery-close" t-on-click="closeGallery">×</button>
                        <img 
                            t-att-src="getImageUrl(state.images[state.currentIndex].id)" 
                            t-att-alt="state.images[state.currentIndex].name"
                            class="image-gallery-main"
                        />
                        <div class="image-gallery-controls">
                            <button 
                                class="image-gallery-btn" 
                                t-on-click="prevImage"
                                t-att-disabled="state.currentIndex === 0"
                            >‹</button>
                            <button 
                                class="image-gallery-btn" 
                                t-on-click="nextImage"
                                t-att-disabled="state.currentIndex === state.images.length - 1"
                            >›</button>
                        </div>
                    </div>
                </div>
            </t>
        </div>
    </t>
</templates>
```

## ./static/src/xml/image_preview_widget.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="stock_lot_dimensions.ImagePreviewWidget" owl="1">
        <div class="image-preview-wrapper" t-if="imageUrl">
            <img 
                t-att-src="imageUrl" 
                class="image-preview-thumbnail"
                t-on-click="openPreview"
                alt="Fotografía"
            />
            
            <t t-if="state.showModal">
                <div class="image-preview-modal" t-on-click="closePreview">
                    <div class="image-preview-content" t-on-click.stop="">
                        <button class="image-preview-close" t-on-click="closePreview">×</button>
                        <img 
                            t-att-src="imageUrl" 
                            class="image-preview-full"
                            alt="Fotografía"
                        />
                    </div>
                </div>
            </t>
        </div>
        <div t-else="" class="image-preview-placeholder">
            <i class="fa fa-picture-o"></i>
        </div>
    </t>
</templates>```

## ./static/src/xml/status_icons_widget.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="stock_lot_dimensions.StatusIconsWidget" owl="1">
        <div class="d-flex" style="gap: 6px; align-items: center;">
            <t t-if="estados.reservado">
                <span class="badge bg-success" title="Reservado" style="font-size: 0.75rem;">
                    <i class="fa fa-hand-paper-o"/> Reservado
                </span>
            </t>
            
            <t t-if="estados.entrega">
                <span class="badge bg-info" title="En Orden de Entrega" style="font-size: 0.75rem;">
                    <i class="fa fa-shopping-cart"/> En Entrega
                </span>
            </t>
            
            <t t-if="estados.detalles">
                <button class="btn btn-sm btn-warning" 
                        t-on-click="mostrarDetalles"
                        style="padding: 2px 6px; font-size: 0.75rem;">
                    <i class="fa fa-info-circle"/> Detalles
                </button>
            </t>
            
            <t t-if="!estados.reservado and !estados.entrega and !estados.detalles">
                <span class="text-muted">—</span>
            </t>
        </div>
    </t>
</templates>```

## ./views/project_project_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_project_project_form_inherit_marmol" model="ir.ui.view">
        <field name="name">project.project.form.inherit.marmol</field>
        <field name="model">project.project</field>
        <field name="inherit_id" ref="project.edit_project"/>
        <field name="arch" type="xml">
            <field name="name" position="after">
                <field name="x_es_proyecto_marmol"/>
            </field>
        </field>
    </record>

    <record id="action_proyectos_marmol" model="ir.actions.act_window">
        <field name="name">Proyectos de Mármol</field>
        <field name="res_model">project.project</field>
        <field name="view_mode">list,form</field>
        <field name="domain">[('x_es_proyecto_marmol', '=', True)]</field>
        <field name="context">{'default_x_es_proyecto_marmol': True}</field>
    </record>

    <menuitem id="menu_proyectos_marmol"
              name="Proyectos de Mármol"
              parent="stock.menu_stock_config_settings"
              action="action_proyectos_marmol"
              sequence="52"/>
</odoo>```

## ./views/res_partner_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_partner_form_inherit_arquitecto" model="ir.ui.view">
        <field name="name">res.partner.form.inherit.arquitecto</field>
        <field name="model">res.partner</field>
        <field name="inherit_id" ref="base.view_partner_form"/>
        <field name="arch" type="xml">
            <field name="category_id" position="after">
                <field name="x_es_arquitecto"/>
            </field>
        </field>
    </record>

    <record id="action_arquitectos" model="ir.actions.act_window">
        <field name="name">Arquitectos</field>
        <field name="res_model">res.partner</field>
        <field name="view_mode">list,form</field>
        <field name="domain">[('x_es_arquitecto', '=', True)]</field>
        <field name="context">{'default_x_es_arquitecto': True, 'default_company_type': 'person'}</field>
    </record>

    <menuitem id="menu_arquitectos"
              name="Arquitectos"
              parent="stock.menu_stock_config_settings"
              action="action_arquitectos"
              sequence="51"/>
</odoo>```

## ./views/stock_lot_group_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Vista Tree de Grupos -->
    <record id="view_stock_lot_group_tree" model="ir.ui.view">
        <field name="name">stock.lot.group.tree</field>
        <field name="model">stock.lot.group</field>
        <field name="arch" type="xml">
            <list string="Grupos de Lotes">
                <field name="name"/>
                <field name="active"/>
            </list>
        </field>
    </record>

    <!-- Vista Form de Grupos -->
    <record id="view_stock_lot_group_form" model="ir.ui.view">
        <field name="name">stock.lot.group.form</field>
        <field name="model">stock.lot.group</field>
        <field name="arch" type="xml">
            <form string="Grupo de Lote">
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="color" widget="color_picker"/>
                        <field name="active"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <!-- Acción -->
    <record id="action_stock_lot_group" model="ir.actions.act_window">
        <field name="name">Grupos de Lotes</field>
        <field name="res_model">stock.lot.group</field>
        <field name="view_mode">list,form</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                Crear un nuevo grupo/etiqueta
            </p>
        </field>
    </record>

    <!-- Menú -->
    <menuitem id="menu_stock_lot_group"
              name="Grupos de Productos"
              parent="stock.menu_stock_config_settings"
              action="action_stock_lot_group"
              sequence="50"/>
</odoo>```

## ./views/stock_lot_hold_order_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Vista Tree -->
    <record id="view_stock_lot_hold_order_tree" model="ir.ui.view">
        <field name="name">stock.lot.hold.order.tree</field>
        <field name="model">stock.lot.hold.order</field>
        <field name="arch" type="xml">
            <list string="Órdenes de Reserva" default_order="create_date desc">
                <field name="name" decoration-bf="1"/>
                <field name="fecha_orden" widget="datetime"/>
                <field name="partner_id"/>
                <field name="user_id" widget="many2one_avatar_user"/>
                <field name="project_id" optional="show"/>
                <field name="arquitecto_id" optional="hide"/>
                <field name="total_placas" sum="Total Placas"/>
                <field name="total_m2" sum="Total m²"/>
                <field name="fecha_expiracion" widget="datetime"/>
                <field name="dias_restantes" 
                       decoration-danger="state == 'confirmed' and dias_restantes &lt;= 3"
                       decoration-warning="state == 'confirmed' and dias_restantes &lt;= 5 and dias_restantes &gt; 3"
                       optional="show"/>
                <field name="state" 
                       decoration-info="state == 'draft'"
                       decoration-success="state == 'confirmed'"
                       decoration-muted="state in ('done', 'cancel')"
                       widget="badge"/>
                <field name="company_id" groups="base.group_multi_company" optional="hide"/>
            </list>
        </field>
    </record>

    <!-- Vista Form -->
    <record id="view_stock_lot_hold_order_form" model="ir.ui.view">
        <field name="name">stock.lot.hold.order.form</field>
        <field name="model">stock.lot.hold.order</field>
        <field name="arch" type="xml">
            <form string="Orden de Reserva">
                <header>
                    <!-- Botón de Imprimir -->
                    <button name="%(action_report_stock_lot_hold_order)d" 
                            string="Imprimir" 
                            type="action" 
                            class="btn-secondary"
                            icon="fa-print"
                            invisible="state == 'draft'"/>
                    
                    <!-- Botón Confirmar -->
                    <button name="action_confirm" 
                            string="Confirmar Reserva" 
                            type="object" 
                            class="btn-primary"
                            invisible="state != 'draft'"
                            confirm="¿Confirmar esta reserva? Se crearán los holds individuales para cada placa."/>
                    
                    <!-- Botón Renovar -->
                    <button name="action_renew" 
                            string="Renovar 5 Días" 
                            type="object" 
                            class="btn-warning"
                            invisible="state != 'confirmed'"
                            confirm="¿Renovar esta reserva por 5 días hábiles adicionales?"/>
                    
                    <!-- Botón Finalizar -->
                    <button name="action_done" 
                            string="Finalizar" 
                            type="object"
                            invisible="state != 'confirmed'"
                            confirm="¿Finalizar esta reserva? Las placas quedarán liberadas."/>
                    
                    <!-- Botón Cancelar -->
                    <button name="action_cancel" 
                            string="Cancelar" 
                            type="object"
                            invisible="state in ('done', 'cancel')"
                            confirm="¿Cancelar esta reserva? Se cancelarán todos los holds asociados."/>
                    
                    <!-- Barra de estado -->
                    <field name="state" widget="statusbar" statusbar_visible="draft,confirmed,done"/>
                </header>
                
                <sheet>
                    <!-- Título con nombre de la orden -->
                    <div class="oe_title">
                        <h1>
                            <field name="name" readonly="1" class="oe_inline"/>
                        </h1>
                        <div class="o_row" invisible="state == 'draft'">
                            <span class="badge badge-pill" 
                                  t-attf-class="badge-{{state == 'confirmed' and 'success' or state == 'done' and 'info' or 'secondary'}}">
                                <field name="state" readonly="1"/>
                            </span>
                        </div>
                    </div>
                    
                    <!-- Ribbon de advertencia si está por expirar -->
                    <div class="ribbon ribbon-top-right" 
                         invisible="state != 'confirmed' or dias_restantes &gt; 3">
                        <span class="bg-danger">¡Por Expirar!</span>
                    </div>
                    
                    <!-- Información General -->
                    <group>
                        <group string="Información del Cliente">
                            <field name="company_id" 
                                   groups="base.group_multi_company" 
                                   options="{'no_create': True}"
                                   readonly="1"/>
                            <field name="partner_id" 
                                   options="{'no_create_edit': True}"
                                   context="{'default_customer_rank': 1, 'show_address': 1}"/>
                            <field name="project_id" 
                                   options="{'no_create_edit': True}"
                                   context="{'default_x_es_proyecto_marmol': True}"/>
                            <field name="arquitecto_id" 
                                   options="{'no_create_edit': True}"
                                   context="{'default_x_es_arquitecto': True}"/>
                        </group>
                        
                        <group string="Información de la Reserva">
                            <field name="user_id" 
                                   widget="many2one_avatar_user"
                                   readonly="1"/>
                            <field name="fecha_orden" 
                                   widget="datetime"
                                   readonly="1"/>
                            <field name="fecha_expiracion" 
                                   widget="datetime"
                                   readonly="1"/>
                            <field name="dias_restantes" 
                                   invisible="state != 'confirmed'"
                                   decoration-danger="dias_restantes &lt;= 3"
                                   decoration-warning="dias_restantes &lt;= 5 and dias_restantes &gt; 3"/>
                        </group>
                    </group>
                    
                    <!-- Resumen en tarjetas -->
                    <group string="Resumen de la Reserva" col="2">
                        <group>
                            <div class="o_field_widget o_stat_info">
                                <span class="o_stat_value">
                                    <field name="total_placas" widget="integer"/>
                                </span>
                                <span class="o_stat_text">Placas Reservadas</span>
                            </div>
                        </group>
                        <group>
                            <div class="o_field_widget o_stat_info">
                                <span class="o_stat_value">
                                    <field name="total_m2" widget="float" options="{'precision': 2}"/>
                                </span>
                                <span class="o_stat_text">Metros Cuadrados</span>
                            </div>
                        </group>
                    </group>
                    
                    <!-- Notebook con pestañas -->
                    <notebook>
                        <!-- Pestaña de Placas Reservadas -->
                        <page string="Placas Reservadas" name="lines">
                            <field name="hold_line_ids">
                                <tree editable="bottom" decoration-muted="hold_id != False">
                                    <field name="sequence" widget="handle"/>
                                    
                                    <field name="quant_id" column_invisible="1"/>
                                    
                                    <field name="lot_id" 
                                           required="1" 
                                           domain="[('product_id', '!=', False)]"
                                           options="{'no_create': True}"/>
                                    
                                    <field name="product_id" 
                                           readonly="1" 
                                           force_save="1"/>
                                    
                                    <field name="cantidad_m2" 
                                           string="m²" 
                                           sum="Total m²" 
                                           readonly="1" 
                                           force_save="1"/>
                                    
                                    <field name="x_grosor" 
                                           string="Grosor" 
                                           optional="show" 
                                           readonly="1"/>
                                    
                                    <field name="x_alto" 
                                           string="Alto" 
                                           optional="show" 
                                           readonly="1"/>
                                    
                                    <field name="x_ancho" 
                                           string="Ancho" 
                                           optional="show" 
                                           readonly="1"/>
                                    
                                    <field name="x_bloque" 
                                           string="Bloque" 
                                           optional="show" 
                                           readonly="1"/>
                                    
                                    <field name="x_tipo" 
                                           string="Tipo" 
                                           optional="show" 
                                           readonly="1" 
                                           widget="badge" 
                                           decoration-info="x_tipo == 'placa'" 
                                           decoration-secondary="x_tipo == 'formato'"/>
                                    
                                    <field name="hold_id" 
                                           string="Hold Creado" 
                                           readonly="1" 
                                           optional="show" 
                                           widget="badge" 
                                           decoration-success="hold_id != False"/>
                                </tree>
                            </field>
                            
                            <!-- Mensaje de ayuda cuando no hay líneas -->
                            <div class="alert alert-info text-center" 
                                 role="alert" 
                                 invisible="hold_line_ids">
                                <p class="mb-0">
                                    <i class="fa fa-info-circle"/> 
                                    Agregue las placas que desea reservar haciendo clic en "Agregar una línea"
                                </p>
                            </div>
                        </page>
                        
                        <!-- Pestaña de Notas -->
                        <page string="Notas" name="notes">
                            <field name="notas" 
                                   placeholder="Ingrese notas adicionales sobre esta reserva...&#10;&#10;Ejemplos:&#10;- Cotización asociada&#10;- Instrucciones especiales de manejo&#10;- Observaciones del cliente&#10;- Etc."/>
                        </page>
                        
                        <!-- Pestaña de Información Adicional -->
                        <page string="Información Adicional" name="additional_info">
                            <group>
                                <group string="Fechas">
                                    <label for="fecha_orden"/>
                                    <div>
                                        <field name="fecha_orden" 
                                               widget="datetime" 
                                               readonly="1" 
                                               class="oe_inline"/>
                                    </div>
                                    
                                    <label for="fecha_expiracion"/>
                                    <div>
                                        <field name="fecha_expiracion" 
                                               widget="datetime" 
                                               readonly="1" 
                                               class="oe_inline"/>
                                        <span invisible="state != 'confirmed'" 
                                              class="ms-2">
                                            (<field name="dias_restantes" 
                                                   class="oe_inline"/> días hábiles restantes)
                                        </span>
                                    </div>
                                </group>
                                
                                <group string="Totales">
                                    <field name="total_placas" readonly="1"/>
                                    <field name="total_m2" readonly="1"/>
                                </group>
                            </group>
                            
                            <!-- Información de auditoría -->
                            <group string="Información de Auditoría" groups="base.group_no_one">
                                <field name="create_uid" readonly="1"/>
                                <field name="create_date" readonly="1"/>
                                <field name="write_uid" readonly="1"/>
                                <field name="write_date" readonly="1"/>
                            </group>
                        </page>
                    </notebook>
                </sheet>
                
                <!-- Chatter -->
                <div class="oe_chatter">
                    <field name="message_follower_ids" 
                           groups="base.group_user"/>
                    <field name="activity_ids"/>
                    <field name="message_ids"/>
                </div>
            </form>
        </field>
    </record>

    <!-- Vista Kanban -->
    <record id="view_stock_lot_hold_order_kanban" model="ir.ui.view">
        <field name="name">stock.lot.hold.order.kanban</field>
        <field name="model">stock.lot.hold.order</field>
        <field name="arch" type="xml">
            <kanban class="o_kanban_mobile" default_order="create_date desc">
                <field name="name"/>
                <field name="partner_id"/>
                <field name="user_id"/>
                <field name="fecha_orden"/>
                <field name="fecha_expiracion"/>
                <field name="total_placas"/>
                <field name="total_m2"/>
                <field name="state"/>
                <field name="dias_restantes"/>
                
                <templates>
                    <t t-name="card">
                        <div class="oe_kanban_card oe_kanban_global_click">
                            <div class="o_kanban_record_top">
                                <div class="o_kanban_record_headings">
                                    <strong class="o_kanban_record_title">
                                        <field name="name"/>
                                    </strong>
                                    <div class="o_kanban_record_subtitle text-muted">
                                        <field name="partner_id"/>
                                    </div>
                                </div>
                                <span class="float-end badge rounded-pill"
                                      t-attf-class="badge-{{record.state.raw_value === 'draft' ? 'secondary' : record.state.raw_value === 'confirmed' ? 'success' : record.state.raw_value === 'done' ? 'info' : 'danger'}}">
                                    <field name="state"/>
                                </span>
                            </div>
                            
                            <div class="o_kanban_record_body">
                                <div class="row">
                                    <div class="col-6">
                                        <span class="fa fa-cubes"/> 
                                        <field name="total_placas"/> placas
                                    </div>
                                    <div class="col-6">
                                        <span class="fa fa-arrows-alt"/> 
                                        <field name="total_m2"/> m²
                                    </div>
                                </div>
                            </div>
                            
                            <div class="o_kanban_record_bottom">
                                <div class="oe_kanban_bottom_left">
                                    <field name="user_id" widget="many2one_avatar_user"/>
                                </div>
                                <div class="oe_kanban_bottom_right">
                                    <span t-if="record.state.raw_value === 'confirmed'" 
                                          class="badge"
                                          t-attf-class="badge-{{record.dias_restantes.raw_value &lt;= 3 ? 'danger' : record.dias_restantes.raw_value &lt;= 5 ? 'warning' : 'info'}}">
                                        <i class="fa fa-clock-o"/> 
                                        <field name="dias_restantes"/> días
                                    </span>
                                </div>
                            </div>
                        </div>
                    </t>
                </templates>
            </kanban>
        </field>
    </record>

    <!-- Vista de búsqueda con filtros -->
    <record id="view_stock_lot_hold_order_search" model="ir.ui.view">
        <field name="name">stock.lot.hold.order.search</field>
        <field name="model">stock.lot.hold.order</field>
        <field name="arch" type="xml">
            <search string="Buscar Órdenes de Reserva">
                <!-- Campos de búsqueda -->
                <field name="name" string="Número"/>
                <field name="partner_id" string="Cliente"/>
                <field name="user_id" string="Vendedor"/>
                <field name="project_id" string="Proyecto"/>
                <field name="arquitecto_id" string="Arquitecto"/>
                
                <!-- Filtros predefinidos -->
                <filter string="Borradores" 
                        name="draft" 
                        domain="[('state', '=', 'draft')]"/>
                
                <filter string="Confirmadas" 
                        name="confirmed" 
                        domain="[('state', '=', 'confirmed')]"/>
                
                <filter string="Finalizadas" 
                        name="done" 
                        domain="[('state', '=', 'done')]"/>
                
                <separator/>
                
                <filter string="Por Expirar (3 días)" 
                        name="expiring_soon" 
                        domain="[('state', '=', 'confirmed'), ('dias_restantes', '&lt;=', 3)]"/>
                
                <filter string="Mis Reservas" 
                        name="my_orders" 
                        domain="[('user_id', '=', uid)]"/>
                
                <separator/>
                
                <filter string="Este Mes" 
                        name="this_month"
                        domain="[('fecha_orden', '&gt;=', (context_today() - relativedelta(day=1)).strftime('%Y-%m-%d')),
                                ('fecha_orden', '&lt;=', (context_today() + relativedelta(months=1, day=1, days=-1)).strftime('%Y-%m-%d'))]"/>
                
                <filter string="Esta Semana" 
                        name="this_week"
                        domain="[('fecha_orden', '&gt;=', (context_today() - relativedelta(weeks=1)).strftime('%Y-%m-%d'))]"/>
                
                <separator/>
                
                <filter string="Fecha de Orden" 
                        name="fecha_orden" 
                        date="fecha_orden"/>
                
                <!-- Agrupaciones -->
                <group expand="0" string="Agrupar por">
                    <filter string="Estado" 
                            name="group_state" 
                            context="{'group_by': 'state'}"/>
                    <filter string="Cliente" 
                            name="group_partner" 
                            context="{'group_by': 'partner_id'}"/>
                    <filter string="Vendedor" 
                            name="group_user" 
                            context="{'group_by': 'user_id'}"/>
                    <filter string="Proyecto" 
                            name="group_project" 
                            context="{'group_by': 'project_id'}"/>
                    <filter string="Fecha de Orden" 
                            name="group_fecha_orden" 
                            context="{'group_by': 'fecha_orden'}"/>
                    <filter string="Compañía" 
                            name="group_company" 
                            context="{'group_by': 'company_id'}"
                            groups="base.group_multi_company"/>
                </group>
            </search>
        </field>
    </record>

    <!-- Acción de ventana -->
    <record id="action_stock_lot_hold_order" model="ir.actions.act_window">
        <field name="name">Órdenes de Reserva</field>
        <field name="res_model">stock.lot.hold.order</field>
        <field name="view_mode">kanban,list,form</field>
        <field name="search_view_id" ref="view_stock_lot_hold_order_search"/>
        <field name="context">{
            'search_default_confirmed': 1,
            'search_default_this_month': 1
        }</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                Crear una nueva orden de reserva
            </p>
            <p>
                Las órdenes de reserva le permiten apartar múltiples placas de mármol
                para un cliente específico durante un período de tiempo determinado.
            </p>
        </field>
    </record>

    <!-- Menú Principal -->
    <menuitem id="menu_stock_lot_hold_order"
              name="Órdenes de Reserva"
              parent="stock.menu_stock_warehouse_mgmt"
              action="action_stock_lot_hold_order"
              sequence="99"/>

    <!-- Renombrar menú anterior de holds individuales -->
    <record id="stock_lot_hold.menu_stock_lot_hold" model="ir.ui.menu">
        <field name="name">Holds Individuales (Técnico)</field>
        <field name="sequence">101</field>
    </record>
</odoo>```

## ./views/stock_lot_hold_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_stock_lot_hold_tree" model="ir.ui.view">
        <field name="name">stock.lot.hold.tree</field>
        <field name="model">stock.lot.hold</field>
        <field name="arch" type="xml">
            <list string="Reservas de Lotes">
                <field name="company_id" groups="base.group_multi_company" optional="show"/>
                <field name="lot_id"/>
                <field name="producto_id"/>
                <field name="partner_id"/>
                <field name="user_id"/>
                <field name="project_id"/>
                <field name="arquitecto_id"/>
                <field name="fecha_inicio"/>
                <field name="fecha_expiracion"/>
                <field name="dias_restantes" 
                       decoration-danger="dias_restantes &lt;= 3"
                       decoration-warning="dias_restantes &lt;= 5 and dias_restantes &gt; 3"/>
                <field name="estado" 
                       decoration-success="estado == 'activo'"
                       decoration-danger="estado == 'expirado'"
                       decoration-muted="estado == 'cancelado'"/>
            </list>
        </field>
    </record>

    <record id="view_stock_lot_hold_form" model="ir.ui.view">
        <field name="name">stock.lot.hold.form</field>
        <field name="model">stock.lot.hold</field>
        <field name="arch" type="xml">
            <form string="Reserva de Lote">
                <header>
                    <button name="action_renovar_hold" 
                            string="Renovar Reserva" 
                            type="object" 
                            class="btn-primary"
                            invisible="estado != 'activo'"/>
                    <button name="action_cancelar_hold" 
                            string="Cancelar Reserva" 
                            type="object" 
                            class="btn-warning"
                            confirm="¿Está seguro de cancelar esta reserva?"
                            invisible="estado != 'activo'"/>
                    <field name="estado" widget="statusbar"/>
                </header>
                <sheet>
                    <group>
                        <group string="Información del Lote">
                            <field name="company_id" groups="base.group_multi_company" options="{'no_create': True}" readonly="1"/>
                            <field name="lot_id"/>
                            <field name="producto_id"/>
                            <field name="ubicacion_id"/>
                        </group>
                        <group string="Información de Reserva">
                            <field name="user_id"/>
                            <field name="partner_id"/>
                            <field name="project_id"/>
                            <field name="arquitecto_id"/>
                        </group>
                    </group>
                    <group>
                        <group string="Fechas">
                            <field name="fecha_inicio"/>
                            <field name="fecha_expiracion"/>
                            <field name="dias_restantes"/>
                        </group>
                        <group string="Notas">
                            <field name="notas" nolabel="1"/>
                        </group>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="action_stock_lot_hold" model="ir.actions.act_window">
        <field name="name">Reservas de Lotes</field>
        <field name="res_model">stock.lot.hold</field>
        <field name="view_mode">list,form</field>
    </record>

    <menuitem id="menu_stock_lot_hold"
              name="Reservas de Lotes"
              parent="stock.menu_stock_warehouse_mgmt"
              action="action_stock_lot_hold"
              sequence="100"/>
</odoo>```

## ./views/stock_lot_hold_wizard_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_stock_lot_hold_wizard_form" model="ir.ui.view">
        <field name="name">stock.lot.hold.wizard.form</field>
        <field name="model">stock.lot.hold.wizard</field>
        <field name="arch" type="xml">
            <form string="Reservar Lote">
                <group>
                    <group string="Información del Lote">
                        <field name="lot_id" readonly="1"/>
                        <field name="producto_id" readonly="1"/>
                        <field name="ubicacion_id" readonly="1"/>
                        <field name="cantidad_disponible" readonly="1"/>
                    </group>
                    
                    <group string="Dimensiones">
                        <field name="x_grosor" readonly="1"/>
                        <field name="x_alto" readonly="1"/>
                        <field name="x_ancho" readonly="1"/>
                        <field name="x_bloque" readonly="1"/>
                        <field name="x_atado" readonly="1"/>
                    </group>
                </group>
                
                <group>
                    <group string="Información de Reserva">
                        <field name="user_id"/>
                        <field name="partner_id" options="{'no_open': True}" context="{'default_customer_rank': 1}"/>
                        <field name="project_id" invisible="project_name"/>
                        <field name="project_name" placeholder="O ingrese nuevo proyecto..." invisible="project_id"/>
                        <field name="arquitecto_id" invisible="arquitecto_name"/>
                        <field name="arquitecto_name" placeholder="O ingrese nuevo arquitecto..." invisible="arquitecto_id"/>
                        <field name="fecha_expiracion" readonly="1"/>
                    </group>
                    
                    <group string="Notas">
                        <field name="notas" 
                               nolabel="1" 
                               placeholder="Ej: Para proyecto X, Cotización Y, etc."/>
                    </group>
                </group>
                
                <div class="alert alert-info" role="alert">
                    <strong>Campos obligatorios:</strong> Vendedor, Cliente, Proyecto y Arquitecto son requeridos para crear la reserva.
                    La reserva expirará automáticamente en 10 días.
                </div>
                
                <footer>
                    <button name="action_crear_hold" 
                            string="Crear Reserva" 
                            type="object" 
                            class="btn-primary"/>
                    <button string="Cancelar" 
                            class="btn-secondary" 
                            special="cancel"/>
                </footer>
                
                <field name="quant_id" invisible="1"/>
            </form>
        </field>
    </record>
</odoo>```

## ./views/stock_lot_image_wizard_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_stock_lot_image_wizard_form" model="ir.ui.view">
        <field name="name">stock.lot.image.wizard.form</field>
        <field name="model">stock.lot.image.wizard</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <div class="oe_title">
                        <h1>
                            <field name="lot_id" readonly="1" class="oe_inline"/>
                        </h1>
                    </div>
                    
                    <group>
                        <group>
                            <field name="name" placeholder="Ej: Foto frontal, Foto lateral, etc."/>
                            <field name="sequence"/>
                        </group>
                        <group>
                            <field name="notas" placeholder="Notas adicionales sobre esta fotografía..."/>
                        </group>
                    </group>
                    
                    <group string="Imagen">
                        <field name="image" 
                               widget="image" 
                               class="oe_avatar" 
                               options="{'preview_image': 'image', 'size': [400, 400]}"/>
                    </group>
                </sheet>
                <footer>
                    <button string="Guardar y Cerrar" 
                            name="action_save_image" 
                            type="object" 
                            class="btn-primary"/>
                    <button string="Cancelar" 
                            class="btn-secondary" 
                            special="cancel"/>
                </footer>
            </form>
        </field>
    </record>
</odoo>```

## ./views/stock_lot_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Vista de formulario mejorada del lote -->
    <record id="view_production_lot_form_inherit" model="ir.ui.view">
        <field name="name">stock.lot.form.inherit.dimensions</field>
        <field name="model">stock.lot</field>
        <field name="inherit_id" ref="stock.view_production_lot_form"/>
        <field name="arch" type="xml">
            <!-- Agregar botón smartbutton para ver fotografías -->
            <div name="button_box" position="inside">
                <button class="oe_stat_button" 
                        type="object" 
                        name="action_view_images" 
                        icon="fa-camera"
                        invisible="x_cantidad_fotos == 0">
                    <field name="x_cantidad_fotos" widget="statinfo" string="Fotos"/>
                </button>
            </div>

            <!-- Campos invisibles computados -->
            <field name="product_id" position="after">
                <field name="x_tiene_fotografias" invisible="1"/>
                <field name="x_fotografia_principal" invisible="1"/>
            </field>

            <!-- Sección de Dimensiones y Características -->
            <xpath expr="//group[@name='main_group']" position="after">
                <notebook>
                    <page string="Dimensiones y Características" name="dimensions">
                        <group>
                            <group string="Dimensiones" name="dimensions_group">
                                <field name="x_grosor" 
                                       widget="float" 
                                       placeholder="0.00"/>
                                <field name="x_alto" 
                                       widget="float" 
                                       placeholder="0.0000"/>
                                <field name="x_ancho" 
                                       widget="float" 
                                       placeholder="0.0000"/>
                            </group>

                            <group string="Características" name="characteristics_group">
                                <field name="x_tipo" 
                                       placeholder="Selecciona tipo..."/>
                                <field name="x_bloque" 
                                       placeholder="Identificación del bloque"/>
                                <field name="x_atado" 
                                    placeholder="Identificación del atado"/>
                                <field name="x_grupo" 
                                    widget="many2many_tags" 
                                    options="{'color_field': 'color', 'no_create_edit': True}"
                                    placeholder="Selecciona grupos..."/>
                                <field name="x_pedimento" 
                                    placeholder="Número de pedimento"/>
                                <field name="x_contenedor" 
                                    placeholder="Número de contenedor"/>
                                <field name="x_referencia_proveedor" 
                                    placeholder="Referencia del proveedor"/>
                            </group>
                        </group>

                        <group string="Detalles Adicionales" name="details_group">
                            <field name="x_detalles_placa" 
                                   placeholder="Detalles especiales: rota, barreno, release, etc."
                                   nolabel="1"/>
                        </group>
                    </page>

                    <page string="Fotografías" name="photos" invisible="x_cantidad_fotos == 0">
                        <field name="x_fotografia_ids" 
                               mode="kanban" 
                               nolabel="1">
                            <kanban class="o_kanban_mobile">
                                <field name="id"/>
                                <field name="name"/>
                                <field name="image"/>
                                <field name="sequence"/>
                                <field name="notas"/>
                                <field name="fecha_captura"/>
                                <templates>
                                    <t t-name="card">
                                        <div class="oe_kanban_global_click o_kanban_record_has_image_fill">
                                            <div class="o_kanban_image">
                                                <img t-att-src="kanban_image('stock.lot.image', 'image', record.id.raw_value)" 
                                                     alt="Foto" 
                                                     class="o_image_64_cover"/>
                                            </div>
                                            <div class="oe_kanban_details">
                                                <strong class="o_kanban_record_title">
                                                    <field name="name"/>
                                                </strong>
                                                <div class="o_kanban_record_subtitle">
                                                    <field name="notas"/>
                                                </div>
                                            </div>
                                        </div>
                                    </t>
                                </templates>
                            </kanban>
                            <form string="Fotografía">
                                <sheet>
                                    <group>
                                        <field name="name"/>
                                        <field name="sequence"/>
                                    </group>
                                    <group>
                                        <field name="image" widget="image" class="oe_avatar"/>
                                    </group>
                                    <group>
                                        <field name="notas" placeholder="Notas adicionales..."/>
                                    </group>
                                </sheet>
                            </form>
                        </field>
                    </page>
                </notebook>
            </xpath>
        </field>
    </record>

    <!-- Vista tree de lotes con dimensiones -->
    <record id="view_production_lot_tree_inherit" model="ir.ui.view">
        <field name="name">stock.lot.tree.inherit.dimensions</field>
        <field name="model">stock.lot</field>
        <field name="inherit_id" ref="stock.view_production_lot_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='product_id']" position="after">
                <field name="x_grosor" optional="hide" string="Grosor (cm)"/>
                <field name="x_alto" optional="hide" string="Alto (m)"/>
                <field name="x_ancho" optional="hide" string="Ancho (m)"/>
                <field name="x_tipo" optional="show" string="Tipo"/>
                <field name="x_bloque" optional="show" string="Bloque"/>
                <field name="x_atado" optional="show" string="Atado"/>
                <field name="x_grupo" widget="many2many_tags" optional="show" string="Grupo"/>
                <field name="x_pedimento" optional="show" string="Pedimento"/>
                <field name="x_contenedor" optional="show" string="Contenedor"/>
                <field name="x_referencia_proveedor" optional="show" string="Ref. Proveedor"/>
                <field name="x_fotografia_principal" 
                       widget="image_preview" 
                       options="{'size': [60, 60]}" 
                       optional="hide"/>
                <field name="x_cantidad_fotos" optional="show" string="Fotos"/>
            </xpath>
        </field>
    </record>

   <!-- Vista Kanban independiente para galería de fotos -->
    <record id="view_stock_lot_image_kanban" model="ir.ui.view">
        <field name="name">stock.lot.image.kanban</field>
        <field name="model">stock.lot.image</field>
        <field name="arch" type="xml">
            <kanban string="Fotografías" class="o_kanban_ungrouped">
                <field name="id"/>
                <field name="name"/>
                <field name="image"/>
                <field name="sequence"/>
                <field name="notas"/>
                <field name="fecha_captura"/>
                <templates>
                    <t t-name="card">
                        <div class="oe_kanban_card oe_kanban_global_click" style="width: 280px; height: 380px; margin: 10px; display: inline-block; vertical-align: top;">
                            <div class="o_kanban_image" style="width: 280px; height: 280px; background: #1a1a1a; display: flex; align-items: center; justify-content: center; overflow: hidden; border-radius: 8px 8px 0 0; position: relative;">
                                <img t-att-src="kanban_image('stock.lot.image', 'image', record.id.raw_value)" 
                                     t-att-alt="record.name.value"
                                     style="width: 100%; height: 100%; object-fit: cover; cursor: pointer;"/>
                            </div>
                            <div class="oe_kanban_details" style="padding: 12px; background: #fff; border-radius: 0 0 8px 8px; height: 100px; overflow: hidden;">
                                <div class="o_kanban_record_top" style="margin-bottom: 6px;">
                                    <strong class="o_kanban_record_title" style="font-size: 13px; color: #2c3e50; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                        <field name="name"/>
                                    </strong>
                                </div>
                                <div class="o_kanban_record_body" style="margin-bottom: 6px; color: #7f8c8d; font-size: 12px; max-height: 36px; overflow: hidden; text-overflow: ellipsis;">
                                    <field name="notas"/>
                                </div>
                                <div class="o_kanban_record_bottom">
                                    <span class="text-muted" style="font-size: 11px;">
                                        <i class="fa fa-clock-o"/> 
                                        <field name="fecha_captura" widget="datetime"/>
                                    </span>
                                </div>
                            </div>
                        </div>
                    </t>
                </templates>
            </kanban>
        </field>
    </record>

    <!-- Vista Form para ver foto en tamaño completo -->
    <record id="view_stock_lot_image_form" model="ir.ui.view">
        <field name="name">stock.lot.image.form</field>
        <field name="model">stock.lot.image</field>
        <field name="arch" type="xml">
            <form string="Fotografía">
                <sheet>
                    <div class="oe_title">
                        <h1>
                            <field name="name" placeholder="Nombre de la fotografía"/>
                        </h1>
                    </div>
                    
                    <group>
                        <group>
                            <field name="lot_id" readonly="1"/>
                            <field name="sequence"/>
                            <field name="fecha_captura" readonly="1"/>
                        </group>
                        <group>
                            <field name="notas" placeholder="Notas sobre esta fotografía..."/>
                        </group>
                    </group>
                    
                    <notebook>
                        <page string="Imagen Original">
                            <div style="text-align: center; padding: 20px; background: #f8f9fa;">
                                <field name="image" 
                                       widget="image" 
                                       options="{'size': [0, 0]}"
                                       style="max-width: 100%; height: auto; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-radius: 8px;"/>
                            </div>
                        </page>
                        <page string="Vista Previa">
                            <div style="text-align: center; padding: 20px;">
                                <field name="image_small" 
                                       widget="image" 
                                       readonly="1"
                                       style="max-width: 400px; height: auto;"/>
                            </div>
                        </page>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <!-- Acción para abrir galería de fotos -->
    <record id="action_stock_lot_image_gallery" model="ir.actions.act_window">
        <field name="name">Galería de Fotografías</field>
        <field name="res_model">stock.lot.image</field>
        <field name="view_mode">kanban,form</field>
        <field name="view_id" ref="view_stock_lot_image_kanban"/>
    </record>

</odoo>```

## ./views/stock_move_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Extender vista de líneas de movimiento en recepción -->
    <record id="view_stock_move_line_operation_tree_inherit" model="ir.ui.view">
        <field name="name">stock.move.line.operations.tree.inherit.dimensions</field>
        <field name="model">stock.move.line</field>
        <field name="inherit_id" ref="stock.view_stock_move_line_operation_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='lot_id']" position="after">
                <!-- Campo computed para determinar si es recepción -->
                <field name="x_is_incoming" column_invisible="1"/>
                
                <!-- Campos temporales (editables solo en recepciones) -->
                <field name="x_grosor_temp" 
                       optional="show" 
                       string="Grosor (cm)"
                       readonly="not x_is_incoming"/>
                <field name="x_alto_temp" 
                       optional="show" 
                       string="Alto (m)"
                       readonly="not x_is_incoming"/>
                <field name="x_ancho_temp" 
                       optional="show" 
                       string="Ancho (m)"
                       readonly="not x_is_incoming"/>
                <field name="x_tipo_temp" 
                       optional="show" 
                       string="Tipo"
                       readonly="not x_is_incoming"/>
                <field name="x_bloque_temp" 
                       optional="show" 
                       string="Bloque"
                       readonly="not x_is_incoming"/>
                <field name="x_atado_temp" 
                       optional="show" 
                       string="Atado"
                       readonly="not x_is_incoming"/>
                
                <field name="x_grupo_temp" 
                    widget="many2many_tags"
                    optional="show" 
                    string="Grupo"
                    readonly="not x_is_incoming"/>
                <field name="x_pedimento_temp" 
                    optional="show" 
                    string="Pedimento"
                    readonly="not x_is_incoming"/>
                <field name="x_contenedor_temp" 
                    optional="show" 
                    string="Contenedor"
                    readonly="not x_is_incoming"/>
                <field name="x_referencia_proveedor_temp" 
                    optional="show" 
                    string="Ref. Proveedor"
                    readonly="not x_is_incoming"/>
            </xpath>
        </field>
    </record>

    <!-- Vista tree para historial de movimientos con dimensiones del lote -->
    <record id="view_move_line_tree_inherit_dimensions" model="ir.ui.view">
        <field name="name">stock.move.line.tree.inherit.lot.dimensions</field>
        <field name="model">stock.move.line</field>
        <field name="inherit_id" ref="stock.view_move_line_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='lot_id']" position="after">
                <field name="x_grosor_lote" optional="hide" string="Grosor (cm)"/>
                <field name="x_alto_lote" optional="hide" string="Alto (m)"/>
                <field name="x_ancho_lote" optional="hide" string="Ancho (m)"/>
                <field name="x_tipo_lote" optional="show" string="Tipo"/>
                <field name="x_bloque_lote" optional="show" string="Bloque"/>
                <field name="x_atado_lote" optional="show" string="Atado"/>
                <field name="x_grupo_lote" widget="many2many_tags" optional="show" string="Grupo"/>
                <field name="x_pedimento_lote" optional="show" string="Pedimento"/>
                <field name="x_contenedor_lote" optional="show" string="Contenedor"/>
                <field name="x_referencia_proveedor_lote" optional="show" string="Ref. Proveedor"/>
                <field name="x_fotografia_principal_lote" widget="image_preview" options="{'size': [60, 60]}" optional="hide"/>
                <field name="x_cantidad_fotos_lote" optional="show" string="Fotos"/>
            </xpath>
        </field>
    </record>

    <record id="view_stock_move_operations_form_inherit" model="ir.ui.view">
        <field name="name">stock.move.operations.form.inherit.dimensions</field>
        <field name="model">stock.move</field>
        <field name="inherit_id" ref="stock.view_stock_move_operations"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='move_line_ids']" position="attributes">
                <attribute name="context">{'list_view_ref': 'stock_lot_dimensions.view_stock_move_line_operation_tree_inherit', 'form_view_ref': 'stock_lot_dimensions.view_move_line_mobile_form_inherit', 'default_picking_id': picking_id, 'default_move_id': id, 'default_product_id': product_id, 'default_location_id': location_id, 'default_location_dest_id': location_dest_id, 'default_company_id': company_id, 'active_picking_id': picking_id}</attribute>
            </xpath>
        </field>
    </record>

    <record id="view_move_line_mobile_form_inherit" model="ir.ui.view">
        <field name="name">stock.move.line.mobile.form.inherit.dimensions</field>
        <field name="model">stock.move.line</field>
        <field name="inherit_id" ref="stock.view_move_line_mobile_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='lot_id']" position="after">
                <field name="x_is_incoming" invisible="1"/>
                
                <group string="Dimensiones del Lote" col="2">
                    <field name="x_grosor_temp" 
                           string="Grosor (cm)"
                           readonly="not x_is_incoming"/>
                    <field name="x_alto_temp" 
                           string="Alto (m)"
                           readonly="not x_is_incoming"/>
                    <field name="x_ancho_temp" 
                           string="Ancho (m)"
                           readonly="not x_is_incoming"/>
                    <field name="x_tipo_temp" 
                           string="Tipo"
                           readonly="not x_is_incoming"/>
                    <field name="x_bloque_temp" 
                           string="Bloque"
                           readonly="not x_is_incoming"/>
                    <field name="x_atado_temp" 
                           string="Atado"
                           readonly="not x_is_incoming"/>
                    
                    <field name="x_grupo_temp" 
                        widget="many2many_tags"
                        string="Grupo"
                        readonly="not x_is_incoming"/>
                    <field name="x_pedimento_temp" 
                        string="Pedimento"
                        readonly="not x_is_incoming"/>
                    <field name="x_contenedor_temp" 
                        string="Contenedor"
                        readonly="not x_is_incoming"/>
                    <field name="x_referencia_proveedor_temp" 
                        string="Ref. Proveedor"
                        readonly="not x_is_incoming"/>
                    
                </group>
            </xpath>
            
            <xpath expr="//group[last()]" position="after">
                <group string="Fotografías" invisible="not lot_id">
                    <button name="action_add_photos" 
                            string="Agregar Fotografías" 
                            type="object" 
                            class="btn-primary"
                            invisible="not lot_id"/>
                    <button name="action_view_lot_photos" 
                            string="Ver Fotografías" 
                            type="object" 
                            class="btn-secondary"
                            invisible="not lot_id or not x_cantidad_fotos_lote"/>
                </group>
            </xpath>
        </field>
    </record>
</odoo>```

## ./views/stock_quant_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Vista tree de ubicaciones con dimensiones y hold -->
    <record id="view_stock_quant_tree_inherit" model="ir.ui.view">
        <field name="name">stock.quant.tree.inherit.dimensions</field>
        <field name="model">stock.quant</field>
        <field name="inherit_id" ref="stock.view_stock_quant_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='lot_id']" position="after">
                <field name="x_grosor" optional="hide" string="Grosor (cm)"/>
                <field name="x_alto" optional="hide" string="Alto (m)"/>
                <field name="x_ancho" optional="hide" string="Ancho (m)"/>
                <field name="x_bloque" optional="show" string="Bloque"/>
                <field name="x_tipo" optional="show" string="Tipo"/>
                <field name="x_atado" optional="show" string="Atado"/>
                <field name="x_grupo" widget="many2many_tags" optional="show" string="Grupo"/>
                <field name="x_pedimento" optional="show" string="Pedimento"/>
                <field name="x_contenedor" optional="show" string="Contenedor"/>
                <field name="x_referencia_proveedor" optional="show" string="Ref. Proveedor"/>
                <field name="x_fotografia_principal" widget="image_preview" options="{'size': [60, 60]}" optional="hide"/>
                <field name="x_cantidad_fotos" optional="show" string="Fotos"/>
                
                <!-- Campos invisibles necesarios para el widget -->
                <field name="x_esta_reservado" column_invisible="1"/>
                <field name="x_en_orden_entrega" column_invisible="1"/>
                <field name="x_tiene_detalles" column_invisible="1"/>
                <field name="x_detalles_placa" column_invisible="1"/>
                
                <!-- NUEVOS CAMPOS DE HOLD -->
                <field name="x_tiene_hold" column_invisible="1"/>
                <field name="x_hold_para" optional="show" string="Hold Para"/>
                <field name="x_hold_dias_restantes" optional="show" string="Días Hold"
                       decoration-danger="x_tiene_hold and x_hold_dias_restantes &lt;= 3"
                       decoration-warning="x_tiene_hold and x_hold_dias_restantes &lt;= 5 and x_hold_dias_restantes &gt; 3"/>
                
                <!-- Columna de estado con iconos -->
                <field name="estado_placa" 
                       string="Estado" 
                       widget="status_icons" 
                       nolabel="1"
                       optional="show"/>
            </xpath>
        </field>
    </record>

    <!-- Vista tree editable (para ubicaciones) con botones de hold -->
    <record id="view_stock_quant_tree_editable_inherit" model="ir.ui.view">
        <field name="name">stock.quant.tree.editable.inherit.dimensions</field>
        <field name="model">stock.quant</field>
        <field name="inherit_id" ref="stock.view_stock_quant_tree_editable"/>
        <field name="arch" type="xml">
            <!-- Agregar campos después de lot_id -->
            <xpath expr="//field[@name='lot_id']" position="after">
                <field name="x_grosor" optional="hide" string="Grosor (cm)" readonly="1"/>
                <field name="x_alto" optional="hide" string="Alto (m)" readonly="1"/>
                <field name="x_ancho" optional="hide" string="Ancho (m)" readonly="1"/>
                <field name="x_bloque" optional="show" string="Bloque" readonly="1"/>
                <field name="x_tipo" optional="show" string="Tipo" readonly="1"/>
                <field name="x_atado" optional="show" string="Atado" readonly="1"/>
                <field name="x_grupo" widget="many2many_tags" optional="show" string="Grupo" readonly="1"/>
                <field name="x_pedimento" optional="show" string="Pedimento" readonly="1"/>
                <field name="x_contenedor" optional="show" string="Contenedor" readonly="1"/>
                <field name="x_referencia_proveedor" optional="show" string="Ref. Proveedor" readonly="1"/>
                <field name="x_fotografia_principal" widget="image_preview" options="{'size': [60, 60]}" optional="hide" readonly="1"/>
                <field name="x_cantidad_fotos" optional="show" string="Fotos" readonly="1"/>
                
                <!-- Campos invisibles necesarios para el widget -->
                <field name="x_esta_reservado" column_invisible="1"/>
                <field name="x_en_orden_entrega" column_invisible="1"/>
                <field name="x_tiene_detalles" column_invisible="1"/>
                <field name="x_detalles_placa" column_invisible="1"/>
                
                <!-- NUEVOS CAMPOS DE HOLD -->
                <field name="x_tiene_hold" column_invisible="1"/>
                <field name="x_hold_para" optional="show" string="Hold Para" readonly="1"/>
                <field name="x_hold_dias_restantes" optional="show" string="Días Hold" readonly="1"
                       decoration-danger="x_tiene_hold and x_hold_dias_restantes &lt;= 3"
                       decoration-warning="x_tiene_hold and x_hold_dias_restantes &lt;= 5 and x_hold_dias_restantes &gt; 3"/>
                
                <!-- Columna de estado con iconos -->
                <field name="estado_placa" 
                       string="Estado" 
                       widget="status_icons" 
                       nolabel="1"
                       optional="show"
                       readonly="1"/>
            </xpath>
            
            <!-- Agregar botones de HOLD después del botón de Replenishment -->
            <xpath expr="//button[@name='action_view_orderpoints']" position="after">
                <!-- Botón para crear hold (solo si no tiene hold activo) -->
                <button name="action_crear_hold" 
                        string="Reservar Lote" 
                        type="object" 
                        class="btn-link text-success" 
                        icon="fa-lock"
                        invisible="not lot_id or x_tiene_hold"
                        help="Crear reserva manual para este lote"/>
                
                <!-- Botón para ver hold (solo si tiene hold activo) -->
                <button name="action_ver_hold" 
                        string="Ver Reserva" 
                        type="object" 
                        class="btn-link text-info" 
                        icon="fa-eye"
                        invisible="not x_tiene_hold"
                        help="Ver detalles de la reserva activa"/>
                
                <!-- Botón para cancelar hold (solo si tiene hold activo) -->
                <button name="action_cancelar_hold" 
                        string="Cancelar Hold" 
                        type="object" 
                        class="btn-link text-danger" 
                        icon="fa-times"
                        invisible="not x_tiene_hold"
                        confirm="¿Está seguro de cancelar esta reserva?"
                        help="Cancelar la reserva activa"/>
                
                <!-- Botones existentes de fotos -->
                <button name="action_add_photos" 
                        string="Agregar Foto" 
                        type="object" 
                        class="btn-link" 
                        icon="fa-camera"
                        invisible="not lot_id"/>
                <button name="action_view_lot_photos" 
                        string="Ver Fotos" 
                        type="object" 
                        class="btn-link" 
                        icon="fa-picture-o"
                        invisible="not lot_id or not x_cantidad_fotos"/>
            </xpath>
        </field>
    </record>
</odoo>```

## ./wizard/__init__.py
```py
# -*- coding: utf-8 -*-
from . import stock_lot_image_wizard
from . import stock_lot_hold_wizard```

## ./wizard/stock_lot_hold_wizard.py
```py
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
        string='Notas',
        placeholder='Notas adicionales sobre esta reserva...'
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
            'fecha_expiracion': fecha_expiracion,  # 🔑 AGREGAR AQUÍ
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
        }```

## ./wizard/stock_lot_image_wizard.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockLotImageWizard(models.TransientModel):
    _name = 'stock.lot.image.wizard'
    _description = 'Wizard para agregar fotografías a lotes'

    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        readonly=True
    )
    
    name = fields.Char(
        string='Nombre',
        required=True,
        default='Fotografía'
    )
    
    image = fields.Binary(
        string='Imagen',
        required=True,
        attachment=True
    )
    
    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )
    
    notas = fields.Text(
        string='Notas',
        placeholder='Notas adicionales sobre esta fotografía...'
    )

    def action_save_image(self):
        """Guardar la imagen y cerrar el wizard"""
        self.ensure_one()
        
        # Crear el registro de imagen
        self.env['stock.lot.image'].create({
            'lot_id': self.lot_id.id,
            'name': self.name,
            'image': self.image,
            'sequence': self.sequence,
            'notas': self.notas,
        })
        
        # Retornar notificación de éxito y cerrar
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '¡Éxito!',
                'message': f'Fotografía agregada correctamente al lote {self.lot_id.name}',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }```

