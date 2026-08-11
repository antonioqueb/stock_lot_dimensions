# -*- coding: utf-8 -*-
# models/stock_lot.py
from odoo import models, fields, api
from .utils.dimension_fields import LotDimensionFields
from .utils.photo_helpers import PhotoHelper
# IMPORTACIÓN FALTANTE AGREGADA:
from .utils.hold_validator import HoldValidator 

class StockLot(models.Model):
    _inherit = 'stock.lot'
    
    # ==================== CAMPOS DE DIMENSIONES ====================
    x_grosor = LotDimensionFields.get_dimension_fields()['x_grosor']
    x_alto = LotDimensionFields.get_dimension_fields()['x_alto']
    x_ancho = LotDimensionFields.get_dimension_fields()['x_ancho']
    x_peso = LotDimensionFields.get_dimension_fields()['x_peso']
    
    # ==================== CAMPOS DE CLASIFICACIÓN ====================
    x_tipo = LotDimensionFields.get_classification_fields()['x_tipo']
    x_numero_placa = LotDimensionFields.get_classification_fields()['x_numero_placa']
    x_bloque = LotDimensionFields.get_classification_fields()['x_bloque']
    x_fecha_lote = fields.Date(
        string='Fecha de lote',
        help='Fecha del lote (corte/llegada).',
    )
    x_atado = LotDimensionFields.get_classification_fields()['x_atado']
    x_grupo = LotDimensionFields.get_classification_fields()['x_grupo']
    x_color = LotDimensionFields.get_classification_fields()['x_color']
    
    # ==================== CAMPOS LOGÍSTICOS ====================
    x_pedimento = LotDimensionFields.get_logistics_fields()['x_pedimento']
    x_contenedor = LotDimensionFields.get_logistics_fields()['x_contenedor']
    x_referencia_proveedor = LotDimensionFields.get_logistics_fields()['x_referencia_proveedor']
    x_proveedor = LotDimensionFields.get_logistics_fields()['x_proveedor']
    x_origen = LotDimensionFields.get_logistics_fields()['x_origen']
    
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

    # ==================== BÚSQUEDA OPTIMIZADA ====================
    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """
        Búsqueda optimizada para evitar errores de 'Query too large' en PostgreSQL.
        1. Si no hay contexto de picking, usa la búsqueda nativa.
        2. Si hay contexto, obtiene los IDs válidos en Python (Set).
        3. Realiza la búsqueda SQL solo por nombre y producto (rápido).
        4. Filtra los resultados en memoria (Python) contra la lista de válidos.
        """
        # Odoo 19: la firma nativa usa "domain" (el kwarg "args" ya no existe).
        domain = domain or []
        move_line_id = self.env.context.get('move_line_id')
        
        # 1. Si no venimos de una línea de movimiento, comportamiento normal
        if not move_line_id:
            return super(StockLot, self).name_search(name, domain, operator, limit)
        
        move_line = self.env['stock.move.line'].browse(move_line_id)
        
        # Validar que sea una salida (outgoing) y tenga picking
        if not (move_line.picking_id and move_line.picking_id.picking_type_code == 'outgoing'):
            return super(StockLot, self).name_search(name, domain, operator, limit)
            
        validator = HoldValidator(self.env)
        partner = validator.get_customer_from_picking(move_line)
        
        # Si no hay cliente para validar holds, comportamiento normal
        if not partner:
            return super(StockLot, self).name_search(name, domain, operator, limit)

        # 2. Obtener lista de IDs permitidos (Lógica de Negocio)
        company_id = (
            move_line.picking_id.company_id.id 
            if move_line.picking_id.company_id 
            else self.env.company.id
        )
        
        # Obtenemos la lista y la convertimos a SET para búsqueda O(1) en Python
        # Esto evita pasar una lista de 10,000 IDs a la consulta SQL
        available_lots_ids = set(validator.get_available_lots(
            move_line.product_id.id,
            move_line.location_id.id,
            partner.id,
            company_id
        ))

        # 3. Preparar argumentos para búsqueda SQL ligera
        # Forzamos el producto para reducir el universo de búsqueda inicial en DB
        search_domain = domain + [('product_id', '=', move_line.product_id.id)]
        
        # 4. Buscar candidatos en base de datos (SQL)
        # Pedimos más del límite (x5) para tener margen de descarte tras filtrar en Python
        candidates = self.search(
            search_domain + [('name', operator, name)], 
            limit=limit * 5
        )
        
        # 5. Filtrar en Python (Intersección de conjuntos)
        # Esto es extremadamente rápido en memoria RAM y no carga la DB
        valid_lots = candidates.filtered(lambda l: l.id in available_lots_ids)
        
        # 6. Devolver resultados formateados respetando el límite original.
        # Odoo 19 eliminó name_get(): llamarlo aquí reventaba con
        # AttributeError justo al buscar un lote por nombre en una salida de
        # un cliente con holds activos (camino caliente de despacho).
        return [(lot.id, lot.display_name) for lot in valid_lots[:limit]]

    # ==================== HELPERS ====================
    def som_short_location(self, depth=2):
        """Ubicación actual del lote RECORTADA:
        - depth=N → los últimos N niveles (depth=2 → 'PATIO A/R1').
        - depth=0 → DESDE EL SEGUNDO nivel: la ruta completa omitiendo solo
          la raíz padre ('SOM/PATIO A/R1' → 'PATIO A/R1').
        Usada por reportes y selectores para que la columna no se coma la
        tabla con la ruta completa."""
        self.ensure_one()
        quant = self.quant_ids.filtered(
            lambda q: q.quantity > 0
            and q.location_id.usage == 'internal')[:1]
        if not quant:
            return ''
        parts = [p for p in (quant.location_id.complete_name
                             or quant.location_id.display_name
                             or '').split('/') if p]
        if not parts:
            return ''
        if depth == 0:
            return '/'.join(parts[1:]) if len(parts) > 1 else parts[0]
        return '/'.join(parts[-depth:])

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