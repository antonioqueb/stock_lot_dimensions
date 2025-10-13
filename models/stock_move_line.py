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

    @api.onchange('lot_id')
    def _onchange_lot_id_dimensions(self):
        """Cargar dimensiones del lote si ya existen"""
        if self.lot_id:
            self.x_grosor_temp = self.lot_id.x_grosor
            self.x_alto_temp = self.lot_id.x_alto
            self.x_ancho_temp = self.lot_id.x_ancho
            # Si el lote tiene dimensiones, calcular cantidad
            if self.lot_id.x_alto and self.lot_id.x_ancho:
                self.qty_done = self.lot_id.x_alto * self.lot_id.x_ancho

    @api.onchange('x_alto_temp', 'x_ancho_temp')
    def _onchange_calcular_cantidad(self):
        """Calcular automáticamente qty_done (m²) cuando se ingresan alto y ancho"""
        if self.x_alto_temp and self.x_ancho_temp:
            self.qty_done = self.x_alto_temp * self.x_ancho_temp

    def write(self, vals):
        """Guardar dimensiones en el lote al confirmar"""
        # Primero ejecutar el write original
        result = super().write(vals)
        
        # Después del write, verificar si hay dimensiones que guardar en el lote
        dimension_fields = ['x_grosor_temp', 'x_alto_temp', 'x_ancho_temp']
        has_dimensions = any(field in vals for field in dimension_fields)
        
        # Si se modificó el lote_id o hay dimensiones, actualizar el lote
        if 'lot_id' in vals or has_dimensions:
            for line in self:
                if line.lot_id:
                    lot_vals = {}
                    
                    # Usar los valores actuales de la línea (ya actualizados por el super().write())
                    if line.x_grosor_temp:
                        lot_vals['x_grosor'] = line.x_grosor_temp
                    if line.x_alto_temp:
                        lot_vals['x_alto'] = line.x_alto_temp
                    if line.x_ancho_temp:
                        lot_vals['x_ancho'] = line.x_ancho_temp
                    
                    # Solo actualizar si hay valores que guardar
                    if lot_vals:
                        line.lot_id.write(lot_vals)
        
        # Calcular qty_done si se modifican alto o ancho (evitar recursión)
        if ('x_alto_temp' in vals or 'x_ancho_temp' in vals) and 'qty_done' not in vals:
            for line in self:
                alto = line.x_alto_temp
                ancho = line.x_ancho_temp
                if alto and ancho:
                    # Usar super() para evitar recursión infinita
                    super(StockMoveLine, line).write({'qty_done': alto * ancho})
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Guardar dimensiones en el lote y calcular cantidad al crear"""
        # Calcular cantidad automáticamente si hay alto y ancho
        for vals in vals_list:
            if vals.get('x_alto_temp') and vals.get('x_ancho_temp'):
                # Sobrescribir qty_done con el cálculo de m²
                vals['qty_done'] = vals['x_alto_temp'] * vals['x_ancho_temp']
        
        lines = super().create(vals_list)
        
        # Guardar dimensiones en el lote después de crear la línea
        for line, vals in zip(lines, vals_list):
            if line.lot_id:
                lot_vals = {}
                
                # Usar los valores de la línea recién creada
                if line.x_grosor_temp:
                    lot_vals['x_grosor'] = line.x_grosor_temp
                if line.x_alto_temp:
                    lot_vals['x_alto'] = line.x_alto_temp
                if line.x_ancho_temp:
                    lot_vals['x_ancho'] = line.x_ancho_temp
                
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