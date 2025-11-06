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
        return 'sequence, id'