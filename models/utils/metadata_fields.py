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
        )