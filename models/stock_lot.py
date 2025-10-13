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