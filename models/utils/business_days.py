# models/utils/business_days.py
# -*- coding: utf-8 -*-
"""
Utilidades para cálculo de días hábiles (lunes a viernes)
"""
from datetime import timedelta
from odoo import fields


class BusinessDaysCalculator:
    """Calculadora de días hábiles excluyendo sábados y domingos"""
    
    @staticmethod
    def is_business_day(date):
        """
        Verifica si una fecha es día hábil (lunes a viernes)
        
        Args:
            date: datetime object
            
        Returns:
            bool: True si es día hábil
        """
        return date.weekday() < 5
    
    @staticmethod
    def add_business_days(start_date, days):
        """
        Suma días hábiles a una fecha
        
        Args:
            start_date: datetime - Fecha de inicio
            days: int - Cantidad de días hábiles a sumar
            
        Returns:
            datetime: Fecha resultante
        """
        fecha_actual = start_date
        dias_agregados = 0
        
        while dias_agregados < days:
            fecha_actual += timedelta(days=1)
            if BusinessDaysCalculator.is_business_day(fecha_actual):
                dias_agregados += 1
        
        return fecha_actual
    
    @staticmethod
    def count_business_days(start_date, end_date):
        """
        Cuenta días hábiles entre dos fechas
        
        Args:
            start_date: datetime - Fecha de inicio
            end_date: datetime - Fecha de fin
            
        Returns:
            int: Cantidad de días hábiles
        """
        dias = 0
        fecha_actual = start_date
        
        while fecha_actual.date() < end_date.date():
            if BusinessDaysCalculator.is_business_day(fecha_actual):
                dias += 1
            fecha_actual += timedelta(days=1)
        
        return dias
    
    @staticmethod
    def get_expiration_date(start_date=None, days=5):
        """
        Calcula fecha de expiración sumando días hábiles
        
        Args:
            start_date: datetime - Fecha de inicio (default: ahora)
            days: int - Días hábiles a sumar (default: 5)
            
        Returns:
            datetime: Fecha de expiración
        """
        if start_date is None:
            start_date = fields.Datetime.now()
        
        return BusinessDaysCalculator.add_business_days(start_date, days)