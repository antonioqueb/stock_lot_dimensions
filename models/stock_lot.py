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
    x_color = LotDimensionFields.get_classification_fields()['x_color']
    
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
        return PhotoHelper.build_photo_gallery_action(self.id, self.name)