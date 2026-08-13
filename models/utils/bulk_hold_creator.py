# models/utils/bulk_hold_creator.py
# -*- coding: utf-8 -*-
"""
Creador de holds masivos desde carrito
"""
from odoo import fields
from .business_days import BusinessDaysCalculator
from ..som_date_format import som_format_date
import logging

_logger = logging.getLogger(__name__)


class BulkHoldCreator:
    """Creador de múltiples holds desde carrito de compras"""
    
    def __init__(self, env):
        self.env = env
    
    def create_holds_from_cart(self, partner_id, project_id, architect_id, 
                               selected_lots, notes=None, currency_code='USD', 
                               product_prices=None):
        """
        Crea múltiples holds con validaciones
        
        Args:
            partner_id: int - ID del cliente
            project_id: int - ID del proyecto
            architect_id: int - ID del embajador
            selected_lots: list - IDs de quants
            notes: str - Notas adicionales
            currency_code: str - Código de divisa
            product_prices: dict - Precios por producto
            
        Returns:
            dict: Resultado con éxitos y errores
        """
        # Validar parámetros
        validation_error = self._validate_parameters(
            partner_id, project_id, architect_id, selected_lots
        )
        if validation_error:
            return validation_error
        
        # Calcular fecha de expiración
        fecha_inicio = fields.Datetime.now()
        fecha_expiracion = BusinessDaysCalculator.get_expiration_date(
            fecha_inicio, 
            days=5
        )
        
        # Preparar notas (sin precios)
        hold_notes = notes or ''
        
        # Crear holds
        holds_created, errors = self._create_holds(
            selected_lots,
            partner_id,
            project_id,
            architect_id,
            fecha_inicio,
            fecha_expiracion,
            hold_notes
        )
        
        # Limpiar carrito si hubo éxitos
        if holds_created:
            self._clear_cart()
        
        return {
            'success': len(holds_created),
            'errors': len(errors),
            'holds': holds_created,
            'failed': errors
        }
    
    def _validate_parameters(self, partner_id, project_id, architect_id, selected_lots):
        """Valida parámetros requeridos"""
        if not partner_id or not selected_lots:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Parámetros inválidos'}]
            }
        
        if not project_id:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Debe seleccionar un proyecto'}]
            }
        
        if not architect_id:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Debe seleccionar un embajador'}]
            }
        
        return None
    
    def _create_holds(self, selected_lots, partner_id, project_id, architect_id,
                     fecha_inicio, fecha_expiracion, notes):
        """Crea holds para cada lote seleccionado"""
        holds_created = []
        errors = []
        
        for quant_id in selected_lots:
            quant = self.env['stock.quant'].browse(quant_id)
            
            # Validar quant
            if not quant.exists() or not quant.lot_id:
                errors.append({
                    'quant_id': quant_id,
                    'error': 'Quant no válido o sin lote'
                })
                continue
            
            # Verificar hold existente
            if quant.x_tiene_hold:
                errors.append({
                    'lot_name': quant.lot_id.name,
                    'error': f'Ya apartado para {quant.x_hold_para}'
                })
                continue
            
            # Crear hold
            try:
                hold = self._create_single_hold(
                    quant, partner_id, project_id, architect_id,
                    fecha_inicio, fecha_expiracion, notes
                )
                
                holds_created.append({
                    'lot_name': quant.lot_id.name,
                    'hold_id': hold.id,
                    'expira': som_format_date(hold.fecha_expiracion, with_time=True)
                })
            except Exception as e:
                errors.append({
                    'lot_name': quant.lot_id.name,
                    'error': str(e)
                })
        
        return holds_created, errors
    
    def _create_single_hold(self, quant, partner_id, project_id, architect_id,
                           fecha_inicio, fecha_expiracion, notes):
        """Crea un hold individual"""
        return self.env['stock.lot.hold'].create({
            'lot_id': quant.lot_id.id,
            'quant_id': quant.id,
            'partner_id': partner_id,
            'user_id': self.env.user.id,
            'project_id': project_id,
            'arquitecto_id': architect_id,
            'fecha_inicio': fecha_inicio,
            'fecha_expiracion': fecha_expiracion,
            'notas': notes,
        })
    
    def _clear_cart(self):
        """Limpia el carrito después de crear holds"""
        try:
            self.env['shopping.cart'].clear_cart()
        except Exception as e:
            _logger.warning("Error al limpiar carrito: %s", str(e))