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

    x_tipo = fields.Selection([
        ('placa', 'Placa'),
        ('formato', 'Formato'),
    ], string='Tipo', help='Tipo de producto: Placa o Formato')
    
    
    x_bloque = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen'
    )

    x_atado = fields.Char(
        string='Atado',
        help='Identificación del atado'
    )

    x_grupo = fields.Many2many(
        'stock.lot.group',
        string='Grupo',
        help='Etiquetas de grupo para clasificación'
    )

    x_pedimento = fields.Char(
        string='Pedimento',
        help='Número de pedimento aduanal'
    )

    x_contenedor = fields.Char(
        string='Contenedor',
        help='Número de contenedor'
    )

    x_referencia_proveedor = fields.Char(
        string='Referencia Proveedor',
        help='Referencia del proveedor'
    )
    
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
            record.x_cantidad_fotos = len(record.x_fotografia_ids)

    def action_view_images(self):
        """Abrir vista de galería de imágenes del lote"""
        self.ensure_one()
        return {
            'name': f'Fotografías de {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'kanban,tree,form',
            'domain': [('lot_id', '=', self.id)],
            'context': {
                'default_lot_id': self.id,
                'create': True,
            },
            'target': 'current',
        }