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
        }