# models/utils/plate_status_builder.py
# -*- coding: utf-8 -*-
"""
Constructor de estados visuales para placas
"""
import json


class PlateStatusBuilder:
    """Constructor de estados JSON para widget de visualización"""
    
    @staticmethod
    def build_hold_status(hold_para, dias_restantes):
        """
        Construye estado de hold manual
        
        Args:
            hold_para: str - Nombre del cliente
            dias_restantes: int - Días hábiles restantes
            
        Returns:
            dict: Estado de hold
        """
        dias_texto = (
            f'{dias_restantes} días hábiles' 
            if dias_restantes != 1 
            else '1 día hábil'
        )
        
        css_class = 'text-warning' if dias_restantes <= 2 else 'text-info'
        
        return {
            'type': 'hold',
            'icon': '🔒',
            'label': f'HOLD para {hold_para}',
            'detail': f'Expira en {dias_texto}',
            'class': css_class
        }
    
    @staticmethod
    def build_delivery_status(picking_name):
        """
        Construye estado de orden de entrega
        
        Args:
            picking_name: str - Nombre del picking
            
        Returns:
            dict: Estado de entrega
        """
        return {
            'type': 'delivery',
            'icon': '📦',
            'label': 'En Orden de Entrega',
            'detail': f'Doc: {picking_name}',
            'class': 'text-primary'
        }
    
    @staticmethod
    def build_details_status(detalles_placa):
        """
        Construye estado de detalles especiales
        
        Args:
            detalles_placa: str - Detalles de la placa
            
        Returns:
            dict: Estado de detalles
        """
        detalles_cortos = (
            detalles_placa[:30] + '...' 
            if len(detalles_placa) > 30 
            else detalles_placa
        )
        
        return {
            'type': 'details',
            'icon': '⚠️',
            'label': 'Detalles Especiales',
            'detail': detalles_cortos,
            'class': 'text-danger'
        }
    
    @staticmethod
    def to_json(estados):
        """
        Convierte lista de estados a JSON
        
        Args:
            estados: list - Lista de estados
            
        Returns:
            str or False: JSON string o False si vacío
        """
        return json.dumps(estados) if estados else False