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
                [('placa', 'Placa'), ('formato', 'Formato'), ('pieza', 'Pieza')],
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
            'x_color': fields.Char(
                string='Color',
                help='Color predominante del material'
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
        return all_fields