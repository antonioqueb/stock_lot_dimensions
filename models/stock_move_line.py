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

    @api.onchange('product_id', 'location_id')
    def _onchange_product_location_filter_lots(self):
        """
        Filtrar el dominio de lotes disponibles basado en:
        1. Lotes sin hold (disponibles para todos)
        2. Lotes con hold para el cliente de este picking
        
        Esto hace que en el campo lot_id solo aparezcan lotes válidos.
        Solo aplica en pickings de salida (entregas).
        
        IMPORTANTE: Este es solo un filtro VISUAL para ayudar al usuario.
        NO es una validación - el usuario técnicamente podría seleccionar otro lote,
        pero el sistema automático no asignará lotes con hold gracias al método
        _get_available_quantity en stock_quant.py
        """
        if not self.product_id or not self.picking_id:
            return {}
        
        # Solo aplicar filtro en pickings de salida (entregas)
        if self.picking_id.picking_type_code != 'outgoing':
            return {}
        
        # Obtener el cliente del picking
        cliente_picking = self.picking_id.partner_id
        if self.move_id and self.move_id.sale_line_id:
            cliente_picking = self.move_id.sale_line_id.order_id.partner_id
        
        if not cliente_picking:
            return {}
        
        # Buscar todos los quants del producto en la ubicación
        quants = self.env['stock.quant'].search([
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', self.location_id.id),
            ('quantity', '>', 0),
        ])
        
        # Filtrar lotes válidos:
        # 1. Lotes SIN hold (disponibles para todos)
        # 2. Lotes CON hold pero para ESTE cliente
        lotes_validos = []
        
        for quant in quants:
            if quant.lot_id:
                # Si no tiene hold, está disponible
                if not quant.x_tiene_hold:
                    lotes_validos.append(quant.lot_id.id)
                # Si tiene hold pero es para este cliente, está disponible
                elif quant.x_hold_activo_id and quant.x_hold_activo_id.partner_id == cliente_picking:
                    lotes_validos.append(quant.lot_id.id)
                # Si tiene hold para otro cliente, NO aparece en la lista
        
        # Retornar dominio que filtra los lotes
        if lotes_validos:
            return {
                'domain': {
                    'lot_id': [
                        ('id', 'in', lotes_validos),
                        ('product_id', '=', self.product_id.id)
                    ]
                }
            }
        else:
            # Si no hay lotes válidos, mostrar dominio vacío
            return {
                'domain': {
                    'lot_id': [('id', '=', False)]
                }
            }

    # ✅ ELIMINADO: @api.constrains('lot_id', 'quantity', 'picking_id')
    # Ya NO validamos aquí porque causaba el error al confirmar la orden
    # La restricción real está en stock_quant._get_available_quantity()
    # que previene la asignación automática de lotes con hold

    @api.onchange('lot_id')
    def _onchange_lot_id_dimensions(self):
        """Cargar dimensiones del lote si ya existen"""
        if self.lot_id:
            # Cargar valores en campos temporales
            self.x_grosor_temp = self.lot_id.x_grosor
            self.x_alto_temp = self.lot_id.x_alto
            self.x_ancho_temp = self.lot_id.x_ancho
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
        dimension_fields = ['x_grosor_temp', 'x_alto_temp', 'x_ancho_temp', 'x_bloque_temp', 'x_formato_temp']
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
        }