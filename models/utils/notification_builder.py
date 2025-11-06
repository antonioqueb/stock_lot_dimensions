# models/utils/notification_builder.py
# -*- coding: utf-8 -*-
"""
Constructor de notificaciones de cliente
"""


class NotificationBuilder:
    """Constructor de notificaciones para acciones de Odoo"""
    
    @staticmethod
    def build_success(title, message, sticky=False):
        """
        Construye notificación de éxito
        
        Args:
            title: str - Título de la notificación
            message: str - Mensaje de la notificación
            sticky: bool - Si la notificación permanece en pantalla
            
        Returns:
            dict: Acción de notificación
        """
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'success',
                'sticky': sticky,
            }
        }
    
    @staticmethod
    def build_warning(title, message, sticky=False):
        """Construye notificación de advertencia"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'warning',
                'sticky': sticky,
            }
        }
    
    @staticmethod
    def build_error(title, message, sticky=True):
        """Construye notificación de error"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'danger',
                'sticky': sticky,
            }
        }
    
    @staticmethod
    def build_info(title, message, sticky=False):
        """Construye notificación informativa"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'info',
                'sticky': sticky,
            }
        }