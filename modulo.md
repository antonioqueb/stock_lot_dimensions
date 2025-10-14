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
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Captura dimensiones y fotografías en lotes durante la recepción',
    'description': """
        Módulo minimalista que permite:
        - Capturar dimensiones (grosor, alto, ancho) y fotografías al recepcionar productos
        - Almacenar esta información en los lotes
        - Visualizar atributos en reportes de inventario
        - Mostrar estados de reserva y detalles de placas
    """,
    'author': 'Alphaqueb Consulting',
    'website': 'https://alphaqueb.com',
    'depends': ['stock', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_lot_views.xml',
        'views/stock_move_views.xml',
        'views/stock_quant_views.xml',
        'views/stock_lot_image_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_lot_dimensions/static/src/js/image_gallery_widget.js',
            'stock_lot_dimensions/static/src/js/image_preview_widget.js',
            'stock_lot_dimensions/static/src/js/status_icons_widget.js',
            'stock_lot_dimensions/static/src/css/image_gallery.css',
            'stock_lot_dimensions/static/src/xml/image_gallery.xml',
            'stock_lot_dimensions/static/src/xml/image_preview_widget.xml',
            'stock_lot_dimensions/static/src/xml/status_icons_widget.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}```

## ./models/__init__.py
```py
# -*- coding: utf-8 -*-
from . import stock_lot
from . import stock_lot_image
from . import stock_move_line
from . import stock_quant
from . import stock_picking
```

## ./models/stock_lot.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockLot(models.Model):
    _inherit = 'stock.lot'

    x_grosor = fields.Float(
        string='Grosor (cm)',
        digits=(10, 2),
        help='Grosor del producto en centímetros'
    )
    
    x_alto = fields.Float(
        string='Alto (m)',
        digits=(10, 4),
        help='Alto del producto en metros'
    )
    
    x_ancho = fields.Float(
        string='Ancho (m)',
        digits=(10, 4),
        help='Ancho del producto en metros'
    )
    
    x_acabado = fields.Selection([
        ('pulido', 'Pulido'),
        ('mate', 'Mate'),
        ('busardeado', 'Busardeado'),
        ('sandblasteado', 'Sandblasteado'),
        ('acido_ligero', 'Acido Ligero'),
        ('acido_rugoso', 'Acido Rugoso'),
        ('cepillado', 'Cepillado'),
        ('busardeado_cepillado', 'Busardeado + Cepillado'),
        ('sandblasteado_cepillado', 'Sandblasteado + Cepillado'),
        ('macheteado', 'Macheteado'),
        ('century', 'Century'),
        ('apomazado', 'Apomazado'),
        ('routeado_nivel1', 'Routeado Nivel 1 (2cm)'),
        ('routeado_nivel2', 'Routeado Nivel 2 (4cm)'),
        ('routeado_nivel3', 'Routeado Nivel 3 (6cm)'),
        ('flameado', 'Flameado'),
        ('al_corte', 'Al corte'),
        ('natural', 'Natural'),
        ('tomboleado', 'Tomboleado'),
        ('lino', 'Lino'),
        ('raw', 'Raw'),
        ('bamboo', 'Bamboo'),
        ('r10', 'R10'),
        ('r11', 'R11'),
        ('polvo', 'Polvo'),
        ('liquido', 'Liquido'),
        ('satinado', 'Satinado'),
        ('cepillado_mate', 'Cepillado / Mate'),
        ('cepillado_brillado', 'Cepillado / Brillado'),
        ('rockface', 'Rockface'),
        ('bamboo_alt', 'Bamboo'),
        ('moonface', 'Moonface'),
        ('corte_disco', 'Corte Disco'),
        ('guillotina', 'Guillotina'),
        ('mate_destapado', 'Mate Destapado'),
        ('mate_retapado', 'Mate Retapado'),
        ('sandblasteado_retapado', 'Sandblasteado Retapado'),
        ('pulido_brillado_retapado', 'Pulido Brillado Retapado'),
        ('cepillado_retapado', 'Cepillado Retapado'),
        ('riverwashed', 'Riverwashed'),
        ('slate', 'Slate'),
    ], string='Acabado', help='Tipo de acabado del producto')
    
    x_bloque = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen'
    )
    
    x_formato = fields.Selection([
        ('placa', 'Placa'),
        ('060x120', '0.60 x 1.20 m'),
        ('060x060', '0.60 x 0.60 m'),
        ('060x040', '0.60 x 0.40 m'),
        ('060x020', '0.60 x 0.20 m'),
        ('060x010', '0.60 x 0.10 m'),
        ('060x030', '0.60 x 0.30 m'),
        ('060xll', '0.60 x LL m'),
        ('050xll', '0.50 x LL m'),
        ('040xll', '0.40 x LL m'),
        ('010xll', '0.10 x LL m'),
        ('005xll', '0.05 x LL m'),
        ('080x160', '0.80 x 1.60 m'),
        ('075x150', '0.75 x 1.50 m'),
        ('320x160', '3.20 x 1.60 m'),
        ('020xll', '0.20 x LL m'),
        ('015xll', '0.15 x LL m'),
        ('122x061', '1.22 x 0.61 m'),
        ('100x050', '1.00 x 0.50 m'),
        ('100x025', '1.00 x 0.25 m'),
        ('120x278', '1.20 x 2.78 m'),
        ('300x100', '3.00 x 1.00 m'),
        ('324x162', '3.24 x 1.62 m'),
    ], string='Formato', default='placa', help='Formato del producto')
    
    x_fotografia_ids = fields.One2many(
        'stock.lot.image',
        'lot_id',
        string='Fotografías',
        help='Fotografías del producto/lote'
    )
    
    x_fotografia_principal = fields.Binary(
        string='Foto Principal',
        compute='_compute_fotografia_principal',
        store=False
    )
    
    x_tiene_fotografias = fields.Boolean(
        string='Tiene Fotos',
        compute='_compute_tiene_fotografias',
        store=True
    )
    
    x_cantidad_fotos = fields.Integer(
        string='# Fotos',
        compute='_compute_cantidad_fotos',
        store=True
    )
    
    # ========== NUEVO CAMPO PARA DETALLES ==========
    
    x_detalles_placa = fields.Text(
        string='Detalles de la Placa',
        help='Detalles especiales: rota, barreno, release, etc.'
    )

    @api.depends('x_fotografia_ids')
    def _compute_fotografia_principal(self):
        """Obtener la primera fotografía como principal"""
        for record in self:
            if record.x_fotografia_ids:
                record.x_fotografia_principal = record.x_fotografia_ids[0].image
            else:
                record.x_fotografia_principal = False

    @api.depends('x_fotografia_ids')
    def _compute_tiene_fotografias(self):
        """Verificar si el lote tiene fotografías"""
        for record in self:
            record.x_tiene_fotografias = bool(record.x_fotografia_ids)

    @api.depends('x_fotografia_ids')
    def _compute_cantidad_fotos(self):
        """Contar número de fotografías"""
        for record in self:
            record.x_cantidad_fotos = len(record.x_fotografia_ids)```

## ./models/stock_lot_image.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockLotImage(models.Model):
    _name = 'stock.lot.image'
    _description = 'Fotografías de Lotes'
    _order = 'sequence, id'

    name = fields.Char(
        string='Nombre',
        required=True,
        default='Fotografía'
    )
    
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Orden de visualización de las fotografías'
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        ondelete='cascade',
        index=True
    )
    
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
    
    fecha_captura = fields.Datetime(
        string='Fecha de Captura',
        default=fields.Datetime.now,
        readonly=True
    )
    
    notas = fields.Text(
        string='Notas'
    )

    @api.depends('image')
    def _compute_image_small(self):
        """Generar miniatura de la imagen"""
        for record in self:
            if record.image:
                # Odoo maneja automáticamente el redimensionamiento
                record.image_small = record.image
            else:
                record.image_small = False
```

## ./models/stock_move_line.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    # Campos temporales para captura en recepción
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
    
    x_acabado_temp = fields.Selection([
        ('pulido', 'Pulido'),
        ('mate', 'Mate'),
        ('busardeado', 'Busardeado'),
        ('sandblasteado', 'Sandblasteado'),
        ('acido_ligero', 'Acido Ligero'),
        ('acido_rugoso', 'Acido Rugoso'),
        ('cepillado', 'Cepillado'),
        ('busardeado_cepillado', 'Busardeado + Cepillado'),
        ('sandblasteado_cepillado', 'Sandblasteado + Cepillado'),
        ('macheteado', 'Macheteado'),
        ('century', 'Century'),
        ('apomazado', 'Apomazado'),
        ('routeado_nivel1', 'Routeado Nivel 1 (2cm)'),
        ('routeado_nivel2', 'Routeado Nivel 2 (4cm)'),
        ('routeado_nivel3', 'Routeado Nivel 3 (6cm)'),
        ('flameado', 'Flameado'),
        ('al_corte', 'Al corte'),
        ('natural', 'Natural'),
        ('tomboleado', 'Tomboleado'),
        ('lino', 'Lino'),
        ('raw', 'Raw'),
        ('bamboo', 'Bamboo'),
        ('r10', 'R10'),
        ('r11', 'R11'),
        ('polvo', 'Polvo'),
        ('liquido', 'Liquido'),
        ('satinado', 'Satinado'),
        ('cepillado_mate', 'Cepillado / Mate'),
        ('cepillado_brillado', 'Cepillado / Brillado'),
        ('rockface', 'Rockface'),
        ('bamboo_alt', 'Bamboo'),
        ('moonface', 'Moonface'),
        ('corte_disco', 'Corte Disco'),
        ('guillotina', 'Guillotina'),
        ('mate_destapado', 'Mate Destapado'),
        ('mate_retapado', 'Mate Retapado'),
        ('sandblasteado_retapado', 'Sandblasteado Retapado'),
        ('pulido_brillado_retapado', 'Pulido Brillado Retapado'),
        ('cepillado_retapado', 'Cepillado Retapado'),
        ('riverwashed', 'Riverwashed'),
        ('slate', 'Slate'),
    ], string='Acabado', help='Tipo de acabado del producto (se guardará en el lote)')
    
    x_bloque_temp = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen (se guardará en el lote)'
    )
    
    x_formato_temp = fields.Selection([
        ('placa', 'Placa'),
        ('060x120', '0.60 x 1.20 m'),
        ('060x060', '0.60 x 0.60 m'),
        ('060x040', '0.60 x 0.40 m'),
        ('060x020', '0.60 x 0.20 m'),
        ('060x010', '0.60 x 0.10 m'),
        ('060x030', '0.60 x 0.30 m'),
        ('060xll', '0.60 x LL m'),
        ('050xll', '0.50 x LL m'),
        ('040xll', '0.40 x LL m'),
        ('010xll', '0.10 x LL m'),
        ('005xll', '0.05 x LL m'),
        ('080x160', '0.80 x 1.60 m'),
        ('075x150', '0.75 x 1.50 m'),
        ('320x160', '3.20 x 1.60 m'),
        ('020xll', '0.20 x LL m'),
        ('015xll', '0.15 x LL m'),
        ('122x061', '1.22 x 0.61 m'),
        ('100x050', '1.00 x 0.50 m'),
        ('100x025', '1.00 x 0.25 m'),
        ('120x278', '1.20 x 2.78 m'),
        ('300x100', '3.00 x 1.00 m'),
        ('324x162', '3.24 x 1.62 m'),
    ], string='Formato', default='placa', help='Formato del producto (se guardará en el lote)')
    
    # Campo computed para saber si es recepción
    x_is_incoming = fields.Boolean(
        string='Es Recepción',
        compute='_compute_is_incoming',
        store=False
    )
    
    # Campos related para mostrar en historial de movimientos
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
    
    x_acabado_lote = fields.Selection(
        related='lot_id.x_acabado',
        string='Acabado Lote',
        readonly=True,
        store=False
    )
    
    x_bloque_lote = fields.Char(
        related='lot_id.x_bloque',
        string='Bloque Lote',
        readonly=True,
        store=False
    )
    
    x_formato_lote = fields.Selection(
        related='lot_id.x_formato',
        string='Formato Lote',
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

    @api.depends('picking_id', 'picking_id.picking_type_code')
    def _compute_is_incoming(self):
        """Determinar si la línea pertenece a una recepción"""
        for line in self:
            line.x_is_incoming = line.picking_id and line.picking_id.picking_type_code == 'incoming'

    @api.onchange('lot_id')
    def _onchange_lot_id_dimensions(self):
        """Cargar dimensiones del lote si ya existen"""
        if self.lot_id:
            # Cargar valores en campos temporales
            self.x_grosor_temp = self.lot_id.x_grosor
            self.x_alto_temp = self.lot_id.x_alto
            self.x_ancho_temp = self.lot_id.x_ancho
            self.x_acabado_temp = self.lot_id.x_acabado
            self.x_bloque_temp = self.lot_id.x_bloque
            self.x_formato_temp = self.lot_id.x_formato
            
            # Si el lote tiene dimensiones, calcular cantidad solo en recepciones
            if self.picking_id and self.picking_id.picking_type_code == 'incoming':
                if self.lot_id.x_alto and self.lot_id.x_ancho:
                    self.qty_done = self.lot_id.x_alto * self.lot_id.x_ancho

    @api.onchange('x_alto_temp', 'x_ancho_temp')
    def _onchange_calcular_cantidad(self):
        """Calcular automáticamente qty_done (m²) cuando se ingresan alto y ancho
        Solo aplica en recepciones"""
        if self.picking_id and self.picking_id.picking_type_code == 'incoming':
            if self.x_alto_temp and self.x_ancho_temp:
                self.qty_done = self.x_alto_temp * self.x_ancho_temp

    def write(self, vals):
        """Guardar dimensiones en el lote al confirmar (solo en recepciones)"""
        # Primero ejecutar el write original
        result = super().write(vals)
        
        # Después del write, verificar si hay dimensiones que guardar en el lote
        dimension_fields = ['x_grosor_temp', 'x_alto_temp', 'x_ancho_temp', 'x_acabado_temp', 'x_bloque_temp', 'x_formato_temp']
        has_dimensions = any(field in vals for field in dimension_fields)
        
        # Si se modificó el lote_id o hay dimensiones, actualizar el lote
        # SOLO en operaciones de entrada (recepciones)
        if 'lot_id' in vals or has_dimensions:
            for line in self:
                if line.lot_id and line.picking_id and line.picking_id.picking_type_code == 'incoming':
                    lot_vals = {}
                    
                    # Usar los valores actuales de la línea (ya actualizados por el super().write())
                    if line.x_grosor_temp:
                        lot_vals['x_grosor'] = line.x_grosor_temp
                    if line.x_alto_temp:
                        lot_vals['x_alto'] = line.x_alto_temp
                    if line.x_ancho_temp:
                        lot_vals['x_ancho'] = line.x_ancho_temp
                    if line.x_acabado_temp:
                        lot_vals['x_acabado'] = line.x_acabado_temp
                    if line.x_bloque_temp:
                        lot_vals['x_bloque'] = line.x_bloque_temp
                    if line.x_formato_temp:
                        lot_vals['x_formato'] = line.x_formato_temp
                    
                    # Solo actualizar si hay valores que guardar
                    if lot_vals:
                        line.lot_id.write(lot_vals)
        
        # Calcular qty_done si se modifican alto o ancho (evitar recursión)
        # Solo en recepciones
        if ('x_alto_temp' in vals or 'x_ancho_temp' in vals) and 'qty_done' not in vals:
            for line in self:
                if line.picking_id and line.picking_id.picking_type_code == 'incoming':
                    alto = line.x_alto_temp
                    ancho = line.x_ancho_temp
                    if alto and ancho:
                        # Usar super() para evitar recursión infinita
                        super(StockMoveLine, line).write({'qty_done': alto * ancho})
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Guardar dimensiones en el lote y calcular cantidad al crear (solo en recepciones)"""
        # Calcular cantidad automáticamente si hay alto y ancho (solo en recepciones)
        for vals in vals_list:
            # Verificar si es una recepción antes de calcular
            picking_id = vals.get('picking_id')
            if picking_id:
                picking = self.env['stock.picking'].browse(picking_id)
                if picking.picking_type_code == 'incoming':
                    if vals.get('x_alto_temp') and vals.get('x_ancho_temp'):
                        # Sobrescribir qty_done con el cálculo de m²
                        vals['qty_done'] = vals['x_alto_temp'] * vals['x_ancho_temp']
        
        lines = super().create(vals_list)
        
        # Guardar dimensiones en el lote después de crear la línea
        # SOLO en operaciones de entrada (recepciones)
        for line, vals in zip(lines, vals_list):
            if line.lot_id and line.picking_id and line.picking_id.picking_type_code == 'incoming':
                lot_vals = {}
                
                # Usar los valores de la línea recién creada
                if line.x_grosor_temp:
                    lot_vals['x_grosor'] = line.x_grosor_temp
                if line.x_alto_temp:
                    lot_vals['x_alto'] = line.x_alto_temp
                if line.x_ancho_temp:
                    lot_vals['x_ancho'] = line.x_ancho_temp
                if line.x_acabado_temp:
                    lot_vals['x_acabado'] = line.x_acabado_temp
                if line.x_bloque_temp:
                    lot_vals['x_bloque'] = line.x_bloque_temp
                if line.x_formato_temp:
                    lot_vals['x_formato'] = line.x_formato_temp
                
                if lot_vals:
                    line.lot_id.write(lot_vals)
        
        return lines

    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote"""
        self.ensure_one()
        if not self.lot_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Advertencia',
                    'message': 'Debe seleccionar un lote primero',
                    'type': 'warning',
                }
            }
        
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
            return False
        
        return {
            'name': f'Fotografías - {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'kanban,form',
            'domain': [('lot_id', '=', self.lot_id.id)],
            'context': {
                'default_lot_id': self.lot_id.id,
            }
        }```

## ./models/stock_picking.py
```py
```

## ./models/stock_quant.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    x_grosor = fields.Float(
        related='lot_id.x_grosor',
        string='Grosor (cm)',
        readonly=True,
        store=False
    )
    
    x_alto = fields.Float(
        related='lot_id.x_alto',
        string='Alto (m)',
        readonly=True,
        store=False
    )
    
    x_ancho = fields.Float(
        related='lot_id.x_ancho',
        string='Ancho (m)',
        readonly=True,
        store=False
    )
    
    x_acabado = fields.Selection(
        related='lot_id.x_acabado',
        string='Acabado',
        readonly=True,
        store=False
    )
    
    x_bloque = fields.Char(
        related='lot_id.x_bloque',
        string='Bloque',
        readonly=True,
        store=False
    )
    
    x_formato = fields.Selection(
        related='lot_id.x_formato',
        string='Formato',
        readonly=True,
        store=False
    )
    
    x_fotografia_principal = fields.Binary(
        related='lot_id.x_fotografia_principal',
        string='Foto',
        readonly=True,
        store=False
    )
    
    x_cantidad_fotos = fields.Integer(
        related='lot_id.x_cantidad_fotos',
        string='# Fotos',
        readonly=True,
        store=False
    )
    
    # ========== NUEVOS CAMPOS PARA ESTADOS ==========
    
    x_esta_reservado = fields.Boolean(
        string='Está Reservado',
        compute='_compute_estados_placa',
        store=False,
        help='Indica si el lote está reservado'
    )
    
    x_en_orden_entrega = fields.Boolean(
        string='En Orden de Entrega',
        compute='_compute_estados_placa',
        store=False,
        help='Indica si el lote está en una orden de entrega'
    )
    
    x_tiene_detalles = fields.Boolean(
        string='Tiene Detalles',
        compute='_compute_tiene_detalles',
        store=False,
        help='Indica si el lote tiene detalles especiales'
    )
    
    x_detalles_placa = fields.Text(
        related='lot_id.x_detalles_placa',
        string='Detalles de la Placa',
        readonly=True,
        store=False
    )
    
    estado_placa = fields.Char(
        string='Estado',
        compute='_compute_estado_placa',
        store=False
    )
    
    # ========== MÉTODOS COMPUTE ==========
    
    @api.depends('lot_id', 'reserved_quantity')
    def _compute_estados_placa(self):
        """Calcular si está reservado o en orden de entrega"""
        for quant in self:
            # Verificar si está reservado (tiene cantidad reservada)
            quant.x_esta_reservado = quant.reserved_quantity > 0
            
            # Verificar si está en una orden de entrega (picking en proceso)
            if quant.lot_id:
                en_orden = self.env['stock.move.line'].search([
                    ('lot_id', '=', quant.lot_id.id),
                    ('picking_id.picking_type_code', '=', 'outgoing'),
                    ('picking_id.state', 'in', ['assigned', 'confirmed', 'waiting'])
                ], limit=1)
                quant.x_en_orden_entrega = bool(en_orden)
            else:
                quant.x_en_orden_entrega = False
    
    @api.depends('lot_id.x_detalles_placa')
    def _compute_tiene_detalles(self):
        """Verificar si el lote tiene detalles"""
        for quant in self:
            quant.x_tiene_detalles = bool(quant.lot_id and quant.lot_id.x_detalles_placa)
    
    @api.depends('x_esta_reservado', 'x_en_orden_entrega', 'x_tiene_detalles')
    def _compute_estado_placa(self):
        """Campo dummy para el widget de iconos"""
        for quant in self:
            quant.estado_placa = 'status'
    
    # ========== MÉTODOS DE ACCIÓN ==========
    
    def action_view_lot_photos(self):
        """Ver y gestionar fotografías del lote"""
        self.ensure_one()
        if not self.lot_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Advertencia',
                    'message': 'No hay lote asociado a esta ubicación',
                    'type': 'warning',
                }
            }
        
        return {
            'name': f'Fotografías - {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'kanban,form',
            'domain': [('lot_id', '=', self.lot_id.id)],
            'context': {
                'default_lot_id': self.lot_id.id,
                'default_name': f'Foto - {self.lot_id.name}',
            }
        }
    
    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote desde ubicaciones"""
        self.ensure_one()
        if not self.lot_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Advertencia',
                    'message': 'No hay lote asociado a esta ubicación',
                    'type': 'warning',
                }
            }
        
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
        }```

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
    setup() {
        this.notification = useService("notification");
    }

    get showReserved() {
        // Acceder correctamente a los datos del record
        const record = this.props.record;
        return record.data.x_esta_reservado || false;
    }

    get showInDelivery() {
        const record = this.props.record;
        return record.data.x_en_orden_entrega || false;
    }

    get showDetails() {
        const record = this.props.record;
        return record.data.x_tiene_detalles || false;
    }

    get detailsText() {
        const record = this.props.record;
        return record.data.x_detalles_placa || 'Sin detalles';
    }

    onClickDetails(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        this.notification.add(this.detailsText, {
            title: "Detalles de la Placa",
            type: "info",
        });
    }
}

StatusIconsWidget.template = "stock_lot_dimensions.StatusIconsWidget";
StatusIconsWidget.supportedTypes = ["char"]; // Importante: especificar el tipo de campo

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
        <div class="d-flex align-items-center" style="gap: 8px;">
            <t t-if="showReserved">
                <span class="badge bg-success" 
                      title="Reservado"
                      style="cursor: help; padding: 4px 8px;">
                    <i class="fa fa-hand-paper-o"/>
                </span>
            </t>
            
            <t t-if="showInDelivery">
                <span class="badge bg-info" 
                      title="En Orden de Entrega"
                      style="cursor: help; padding: 4px 8px;">
                    <i class="fa fa-shopping-cart"/>
                </span>
            </t>
            
            <t t-if="showDetails">
                <a href="#" 
                   class="btn btn-sm btn-link p-0" 
                   t-on-click.prevent="onClickDetails"
                   title="Ver Detalles"
                   style="text-decoration: none;">
                    <i class="fa fa-info-circle text-warning" style="font-size: 1.3em;"/>
                </a>
            </t>
            
            <t t-if="!showReserved and !showInDelivery and !showDetails">
                <span class="text-muted" style="font-size: 0.9em;">—</span>
            </t>
        </div>
    </t>
</templates>```

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
    <record id="view_stock_lot_form_inherit" model="ir.ui.view">
        <field name="name">stock.lot.form.inherit.dimensions</field>
        <field name="model">stock.lot</field>
        <field name="inherit_id" ref="stock.view_production_lot_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='product_id']" position="after">
                <group string="Dimensiones" col="4">
                    <field name="x_grosor" string="Grosor (cm)"/>
                    <field name="x_alto" string="Alto (m)"/>
                    <field name="x_ancho" string="Ancho (m)"/>
                    <field name="x_cantidad_fotos" readonly="1"/>
                </group>
                
                <group string="Detalles Especiales">
                    <field name="x_detalles_placa" 
                           placeholder="Ej: Placa rota esquina superior, Barreno en centro, Release pendiente, etc."
                           nolabel="1"/>
                </group>
            </xpath>
            
            <xpath expr="//sheet" position="inside">
                <notebook>
                    <page string="Fotografías" name="fotografias">
                        <field name="x_fotografia_ids" mode="kanban">
                            <kanban>
                                <field name="id"/>
                                <field name="name"/>
                                <field name="image_small"/>
                                <field name="sequence"/>
                                <templates>
                                    <t t-name="kanban-box">
                                        <div class="oe_kanban_global_click" style="text-align: center;">
                                            <div class="o_kanban_image">
                                                <img t-att-src="kanban_image('stock.lot.image', 'image_small', record.id.raw_value)" 
                                                     alt="Fotografía" 
                                                     style="max-width: 150px; max-height: 150px; border: 1px solid #ddd; border-radius: 4px;"/>
                                            </div>
                                            <div class="oe_kanban_details">
                                                <strong><field name="name"/></strong>
                                            </div>
                                        </div>
                                    </t>
                                </templates>
                            </kanban>
                            <form>
                                <sheet>
                                    <group>
                                        <field name="name"/>
                                        <field name="sequence"/>
                                        <field name="fecha_captura" readonly="1"/>
                                    </group>
                                    <group>
                                        <field name="image" widget="image" options="{'size': [800, 600]}"/>
                                    </group>
                                    <group>
                                        <field name="notas" placeholder="Notas adicionales sobre esta fotografía..."/>
                                    </group>
                                </sheet>
                            </form>
                        </field>
                    </page>
                </notebook>
            </xpath>
        </field>
    </record>

    <record id="view_stock_lot_tree_inherit" model="ir.ui.view">
        <field name="name">stock.lot.tree.inherit.dimensions</field>
        <field name="model">stock.lot</field>
        <field name="inherit_id" ref="stock.view_production_lot_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='name']" position="after">
                <field name="x_grosor" optional="hide" string="Grosor (cm)"/>
                <field name="x_alto" optional="hide" string="Alto (m)"/>
                <field name="x_ancho" optional="hide" string="Ancho (m)"/>
                <field name="x_fotografia_principal" widget="image" optional="hide"/>
                <field name="x_cantidad_fotos" optional="show"/>
            </xpath>
        </field>
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
                <field name="x_acabado_temp" 
                       optional="show" 
                       string="Acabado"
                       readonly="not x_is_incoming"/>
                <field name="x_bloque_temp" 
                       optional="show" 
                       string="Bloque"
                       readonly="not x_is_incoming"/>
                <field name="x_formato_temp" 
                       optional="show" 
                       string="Formato"
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
                <field name="x_acabado_lote" optional="show" string="Acabado"/>
                <field name="x_bloque_lote" optional="show" string="Bloque"/>
                <field name="x_formato_lote" optional="show" string="Formato"/>
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
                    <field name="x_acabado_temp" 
                           string="Acabado"
                           readonly="not x_is_incoming"/>
                    <field name="x_bloque_temp" 
                           string="Bloque"
                           readonly="not x_is_incoming"/>
                    <field name="x_formato_temp" 
                           string="Formato"
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
    <!-- Vista tree de ubicaciones con dimensiones -->
    <record id="view_stock_quant_tree_inherit" model="ir.ui.view">
        <field name="name">stock.quant.tree.inherit.dimensions</field>
        <field name="model">stock.quant</field>
        <field name="inherit_id" ref="stock.view_stock_quant_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='lot_id']" position="after">
                <field name="x_grosor" optional="hide" string="Grosor (cm)"/>
                <field name="x_alto" optional="hide" string="Alto (m)"/>
                <field name="x_ancho" optional="hide" string="Ancho (m)"/>
                <field name="x_acabado" optional="show" string="Acabado"/>
                <field name="x_bloque" optional="show" string="Bloque"/>
                <field name="x_formato" optional="show" string="Formato"/>
                <field name="x_fotografia_principal" widget="image_preview" options="{'size': [60, 60]}" optional="hide"/>
                <field name="x_cantidad_fotos" optional="show" string="Fotos"/>
                
                <!-- Campos invisibles necesarios para el widget -->
                <field name="x_esta_reservado" column_invisible="1"/>
                <field name="x_en_orden_entrega" column_invisible="1"/>
                <field name="x_tiene_detalles" column_invisible="1"/>
                <field name="x_detalles_placa" column_invisible="1"/>
                
                <!-- Columna de estado con iconos -->
                <field name="estado_placa" 
                       string="Estado" 
                       widget="status_icons" 
                       nolabel="1"
                       optional="show"/>
            </xpath>
        </field>
    </record>

    <!-- Vista tree editable (para ubicaciones) con botón de fotos -->
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
                <field name="x_acabado" optional="show" string="Acabado" readonly="1"/>
                <field name="x_bloque" optional="show" string="Bloque" readonly="1"/>
                <field name="x_formato" optional="show" string="Formato" readonly="1"/>
                <field name="x_fotografia_principal" widget="image_preview" options="{'size': [60, 60]}" optional="hide" readonly="1"/>
                <field name="x_cantidad_fotos" optional="show" string="Fotos" readonly="1"/>
                
                <!-- Campos invisibles necesarios para el widget -->
                <field name="x_esta_reservado" column_invisible="1"/>
                <field name="x_en_orden_entrega" column_invisible="1"/>
                <field name="x_tiene_detalles" column_invisible="1"/>
                <field name="x_detalles_placa" column_invisible="1"/>
                
                <!-- Columna de estado con iconos -->
                <field name="estado_placa" 
                       string="Estado" 
                       widget="status_icons" 
                       nolabel="1"
                       optional="show"
                       readonly="1"/>
            </xpath>
            
            <!-- Agregar botones después del botón de Replenishment -->
            <xpath expr="//button[@name='action_view_orderpoints']" position="after">
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
from . import stock_lot_image_wizard```

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

