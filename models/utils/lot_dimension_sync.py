# models/utils/lot_dimension_sync.py
# -*- coding: utf-8 -*-
"""
Sincronización de dimensiones temporales con lotes
"""


class LotDimensionSync:
    """Sincronizador de campos temporales de dimensiones al lote"""
    
    # Mapeo de campos temporales a campos del lote
    DIMENSION_MAPPING = {
        'x_grosor_temp': 'x_grosor',
        'x_alto_temp': 'x_alto',
        'x_ancho_temp': 'x_ancho',
        'x_color_temp': 'x_color',
        'x_bloque_temp': 'x_bloque',
        'x_atado_temp': 'x_atado',
        'x_tipo_temp': 'x_tipo',
        'x_pedimento_temp': 'x_pedimento',
        'x_contenedor_temp': 'x_contenedor',
        'x_referencia_proveedor_temp': 'x_referencia_proveedor',
    }
    

    @staticmethod
    def load_dimensions_from_lot(move_line):
        """Carga dimensiones del lote a campos temporales (TODOS los campos)"""
        if not move_line.lot_id:
            return
        
        lot = move_line.lot_id
        move_line.x_color_temp = lot.x_color
        move_line.x_grosor_temp = lot.x_grosor
        move_line.x_alto_temp = lot.x_alto
        move_line.x_ancho_temp = lot.x_ancho
        move_line.x_bloque_temp = lot.x_bloque
        move_line.x_atado_temp = lot.x_atado
        move_line.x_tipo_temp = lot.x_tipo
        # --- AGREGAR ESTOS CAMPOS FALTANTES ---
        move_line.x_pedimento_temp = lot.x_pedimento
        move_line.x_contenedor_temp = lot.x_contenedor
        move_line.x_referencia_proveedor_temp = lot.x_referencia_proveedor
        if lot.x_grupo:
            move_line.x_grupo_temp = [(6, 0, lot.x_grupo.ids)]
    
    @staticmethod
    def sync_dimensions_to_lot(move_line):
        """
        Sincroniza dimensiones temporales al lote
        
        Args:
            move_line: stock.move.line record
            
        Returns:
            dict: Valores a escribir en el lote
        """
        lot_vals = {}
        
        for temp_field, lot_field in LotDimensionSync.DIMENSION_MAPPING.items():
            value = getattr(move_line, temp_field, None)
            if value:
                lot_vals[lot_field] = value
        
        # Campo many2many requiere formato especial
        if move_line.x_grupo_temp:
            lot_vals['x_grupo'] = [(6, 0, move_line.x_grupo_temp.ids)]
        
        return lot_vals
    
    @staticmethod
    def calculate_area(alto, ancho):
        """
        Calcula área en m²
        
        Args:
            alto: float - Alto en metros
            ancho: float - Ancho en metros
            
        Returns:
            float: Área en m²
        """
        if alto and ancho:
            return alto * ancho
        return 0.0
    
    @staticmethod
    def get_available_quantity(env, lot_id, location_id, product_id, move_qty=None):
        """
        Obtiene cantidad disponible de un lote
        
        Args:
            env: Environment
            lot_id: int - ID del lote
            location_id: int - ID de ubicación
            product_id: int - ID del producto
            move_qty: float - Cantidad solicitada en el move
            
        Returns:
            float: Cantidad disponible
        """
        quant = env['stock.quant'].search([
            ('lot_id', '=', lot_id),
            ('location_id', '=', location_id),
            ('product_id', '=', product_id)
        ], limit=1)
        
        if not quant or quant.available_quantity <= 0:
            return 0.0
        
        available = quant.available_quantity
        
        if move_qty:
            return min(available, move_qty)
        
        return available