# -*- coding: utf-8 -*-
# models/stock_quant.py
from odoo import models, fields, api
from odoo.exceptions import UserError
from .utils.plate_status_builder import PlateStatusBuilder
from .utils.bulk_hold_creator import BulkHoldCreator
from .utils.notification_builder import NotificationBuilder
from .utils.photo_helpers import PhotoHelper
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'
    
    # ==================== CAMPOS RELACIONADOS DEL LOTE ====================

    x_color = fields.Char(related='lot_id.x_color', string='Color', readonly=True)
    x_grosor = fields.Float(related='lot_id.x_grosor', string='Grosor', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', string='Alto', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', string='Ancho', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', string='Bloque', readonly=True)
    x_tipo = fields.Selection(related='lot_id.x_tipo', string='Tipo', readonly=True)
    x_atado = fields.Char(related='lot_id.x_atado', string='Atado', readonly=True)
    x_grupo = fields.Many2many(related='lot_id.x_grupo', string='Grupo', readonly=True)
    x_pedimento = fields.Char(related='lot_id.x_pedimento', string='Pedimento', readonly=True)
    x_contenedor = fields.Char(related='lot_id.x_contenedor', string='Contenedor', readonly=True)
    x_referencia_proveedor = fields.Char(related='lot_id.x_referencia_proveedor', string='Ref. Proveedor', readonly=True)
    x_proveedor = fields.Char(related='lot_id.x_proveedor', string='Proveedor', readonly=True)
    x_origen = fields.Char(related='lot_id.x_origen', string='Origen', readonly=True)
    x_fotografia_principal = fields.Binary(related='lot_id.x_fotografia_principal', readonly=True)
    x_cantidad_fotos = fields.Integer(related='lot_id.x_cantidad_fotos', readonly=True)
    x_detalles_placa = fields.Text(related='lot_id.x_detalles_placa', string='Detalles', readonly=True)
    
    # ==================== CAMPOS DE ESTADO DE RESERVA (SISTEMA) ====================
    # Nota: Estos se mantienen store=True porque dependen de stock moves nativos, no de holds manuales
    x_esta_reservado = fields.Boolean(
        string='Reservado (Sistema)',
        compute='_compute_estado_reserva',
        store=True,
        help='Indica si el lote está reservado por el sistema de entregas'
    )
    
    x_en_orden_entrega = fields.Boolean(
        string='En Orden de Entrega',
        compute='_compute_estado_reserva',
        store=True,
        help='Indica si el lote está en una orden de entrega confirmada'
    )
    
    x_tiene_detalles = fields.Boolean(
        string='Tiene Detalles',
        compute='_compute_tiene_detalles',
        store=True,
        help='Indica si la placa tiene detalles especiales registrados'
    )
    
    # ==================== CAMPOS DE HOLD MANUAL (OPTIMIZADOS) ====================
    x_hold_ids = fields.One2many(
        'stock.lot.hold',
        'quant_id',
        string='Reservas Manuales',
        help='Holds/Reservas manuales de este quant'
    )
    
    # CORRECCIÓN: store=False + search method para evitar bloqueos y permitir filtros
    x_tiene_hold = fields.Boolean(
        string='Tiene Hold',
        compute='_compute_estado_hold',
        store=False, 
        search='_search_tiene_hold', # Permite filtrar aunque no esté almacenado
        compute_sudo=True,
        help='Indica si el lote tiene una reserva manual activa'
    )
    
    x_hold_activo_id = fields.Many2one(
        'stock.lot.hold',
        string='Hold Activo',
        compute='_compute_estado_hold',
        store=False,
        search='_search_hold_activo', # Permite buscar por ID de hold
        compute_sudo=True,
        help='Hold activo actualmente en este quant'
    )
    
    x_hold_para = fields.Char(
        string='Reservado Para',
        compute='_compute_estado_hold',
        store=False,
        compute_sudo=True,
        help='Cliente para quien está reservado'
    )
    
    x_hold_expira = fields.Datetime(
        string='Expira',
        compute='_compute_estado_hold',
        store=False,
        compute_sudo=True,
        help='Fecha de expiración del hold'
    )
    
    x_hold_dias_restantes = fields.Integer(
        string='Días Restantes',
        compute='_compute_hold_dias_restantes',
        compute_sudo=True,
        help='Días hábiles restantes del hold'
    )
    
    # ==================== CAMPO DE ESTADO VISUAL ====================
    estado_placa = fields.Char(
        string='Estado Placa',
        compute='_compute_estado_placa',
        help='Estado visual de la placa (JSON para widget)'
    )
    
    # ==================== MÉTODOS DE BÚSQUEDA (SEARCH) ====================
    
    def _search_tiene_hold(self, operator, value):
        """
        Permite filtrar por 'Tiene Hold' sin necesidad de almacenar el campo en BD.
        Busca directamente en la tabla de holds activos.
        """
        if operator not in ['=', '!=']:
            raise UserError('Operación no soportada para el filtro de Hold.')

        # Buscar todos los holds activos
        holds_activos = self.env['stock.lot.hold'].sudo().search([
            ('estado', '=', 'activo')
        ])
        
        # Obtener IDs de los quants afectados
        quants_con_hold_ids = holds_activos.mapped('quant_id').ids

        if (operator == '=' and value) or (operator == '!=' and not value):
            # El usuario busca Verdadero: Retornar quants que ESTÁN en la lista
            return [('id', 'in', quants_con_hold_ids)]
        else:
            # El usuario busca Falso: Retornar quants que NO ESTÁN en la lista
            return [('id', 'not in', quants_con_hold_ids)]

    def _search_hold_activo(self, operator, value):
        """Permite búsquedas relacionadas con el objeto Hold"""
        holds = self.env['stock.lot.hold'].search([
            ('id', operator, value),
            ('estado', '=', 'activo')
        ])
        return [('id', 'in', holds.mapped('quant_id').ids)]

    # ==================== MÉTODOS COMPUTADOS ====================
    @api.depends('lot_id.x_detalles_placa')
    def _compute_tiene_detalles(self):
        """Verificar si la placa tiene detalles especiales"""
        for quant in self:
            quant.x_tiene_detalles = bool(
                quant.x_detalles_placa and 
                quant.x_detalles_placa.strip()
            )
    
    # ==================== MÉTODOS COMPUTADOS OPTIMIZADOS ====================
    
    @api.depends('x_hold_ids.estado', 'company_id')
    def _compute_estado_hold(self):
        """
        Computar el estado del hold manual de forma vectorizada (Batch).
        Evita el problema N+1 y reduce bloqueos de lectura.
        """
        # 1. Preparar estructuras de datos
        quants_with_hold = {}
        
        # Filtramos quants que tienen lotes para no perder tiempo
        quants_to_process = self.filtered(lambda q: q.lot_id)
        
        if not quants_to_process:
            self.x_tiene_hold = False
            self.x_hold_activo_id = False
            self.x_hold_para = False
            self.x_hold_expira = False
            return

        # 2. Buscar Holds Activos en UNA sola consulta para todos los quants
        # Agrupamos por compañía para respetar la lógica original
        company_ids = quants_to_process.mapped('company_id').ids
        if not company_ids:
            company_ids = [self.env.company.id]

        domain = [
            ('quant_id', 'in', quants_to_process.ids),
            ('estado', '=', 'activo'),
            ('company_id', 'in', company_ids) # Ojo con lógica multi-company
        ]
        
        # Obtenemos los holds activos relevantes
        active_holds = self.env['stock.lot.hold'].search(domain, order='create_date desc')
        
        # 3. Mapear Holds a Quants en memoria
        # Usamos un diccionario para acceso rápido: {quant_id: hold_record}
        # Como ordenamos por create_date desc, el primero que procesemos será el más reciente
        for hold in active_holds:
            if hold.quant_id.id not in quants_with_hold:
                # Verificar coincidencia de compañía específica del quant
                quant_company = hold.quant_id.company_id.id or self.env.company.id
                if hold.company_id.id == quant_company:
                    quants_with_hold[hold.quant_id.id] = hold

        # 4. Asignar valores (en memoria)
        for quant in self:
            hold = quants_with_hold.get(quant.id)
            if hold:
                quant.x_tiene_hold = True
                quant.x_hold_activo_id = hold.id
                quant.x_hold_para = hold.partner_id.name
                quant.x_hold_expira = hold.fecha_expiracion
            else:
                quant.x_tiene_hold = False
                quant.x_hold_activo_id = False
                quant.x_hold_para = False
                quant.x_hold_expira = False

    @api.depends('x_hold_activo_id', 'x_hold_activo_id.dias_restantes')
    def _compute_hold_dias_restantes(self):
        """Calcular días restantes optimizado"""
        for quant in self:
            # Al acceder a x_hold_activo_id.dias_restantes, Odoo usa caché si es posible
            if quant.x_hold_activo_id:
                quant.x_hold_dias_restantes = quant.x_hold_activo_id.dias_restantes
            else:
                quant.x_hold_dias_restantes = 0

    
    @api.depends('reserved_quantity', 'quantity', 'lot_id')
    def _compute_estado_reserva(self):
        """Computar si el lote está reservado por el sistema de entregas"""
        for quant in self:
            quant.x_esta_reservado = quant.reserved_quantity > 0
            quant.x_en_orden_entrega = self._check_if_in_delivery_order(quant)
    
    def _check_if_in_delivery_order(self, quant):
        """Verifica si el lote está en una orden de entrega confirmada"""
        if not quant.lot_id or not quant.x_esta_reservado:
            return False
        
        move_line = self.env['stock.move.line'].search([
            ('lot_id', '=', quant.lot_id.id),
            ('location_id', '=', quant.location_id.id),
            ('state', 'in', ['assigned', 'partially_available']),
            ('picking_id.picking_type_code', '=', 'outgoing'),
        ], limit=1)
        
        return bool(move_line)
    
    @api.depends(
        'x_esta_reservado',
        'x_en_orden_entrega',
        'x_tiene_detalles',
        'x_detalles_placa',
        'x_tiene_hold',
        'x_hold_para',
        'x_hold_dias_restantes'
    )
    def _compute_estado_placa(self):
        """Generar JSON con los estados para el widget visual"""
        for quant in self:
            estados = self._build_plate_statuses(quant)
            quant.estado_placa = PlateStatusBuilder.to_json(estados)
    
    def _build_plate_statuses(self, quant):
        """Construye lista de estados de la placa"""
        estados = []
        
        # Hold manual (prioridad más alta)
        if quant.x_tiene_hold:
            estados.append(
                PlateStatusBuilder.build_hold_status(
                    quant.x_hold_para,
                    quant.x_hold_dias_restantes
                )
            )
        # Reserva del sistema (solo si no tiene hold)
        elif quant.x_esta_reservado and quant.x_en_orden_entrega:
            move_line = self._get_delivery_move_line(quant)
            if move_line:
                estados.append(
                    PlateStatusBuilder.build_delivery_status(
                        move_line.picking_id.name
                    )
                )
        
        # Detalles especiales
        if quant.x_tiene_detalles:
            estados.append(
                PlateStatusBuilder.build_details_status(quant.x_detalles_placa)
            )
        
        return estados
    
    def _get_delivery_move_line(self, quant):
        """Obtiene la move line de entrega asociada"""
        return self.env['stock.move.line'].search([
            ('lot_id', '=', quant.lot_id.id),
            ('location_id', '=', quant.location_id.id),
            ('state', 'in', ['assigned', 'partially_available']),
            ('picking_id.picking_type_code', '=', 'outgoing'),
        ], limit=1)
    
    # ==================== ACCIONES DE FOTOGRAFÍAS ====================
    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote"""
        self.ensure_one()
        
        if not self.lot_id:
            raise UserError('Este registro no tiene un lote asignado.')
        
        return {
            'name': f'Agregar Fotografía al Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lot_id': self.lot_id.id}
        }
    
    def action_view_lot_photos(self):
        """Ver las fotografías del lote"""
        self.ensure_one()
        
        if not self.lot_id:
            raise UserError('Este registro no tiene un lote asignado.')
        
        return PhotoHelper.build_photo_gallery_action(self.lot_id.id, self.lot_id.name)
    
    # ==================== ACCIONES DE HOLD ====================
    def action_crear_hold(self):
        """Abrir wizard para crear un hold manual en este quant"""
        self.ensure_one()
        
        if not self.lot_id:
            raise UserError('Este registro no tiene un lote asignado.')
        
        if self.x_tiene_hold:
            dias_texto = (
                f'{self.x_hold_dias_restantes} días hábiles' 
                if self.x_hold_dias_restantes != 1 
                else '1 día hábil'
            )
            raise UserError(
                f'Este lote ya tiene una reserva activa para {self.x_hold_para} '
                f'que expira en {dias_texto}.'
            )
        
        return {
            'name': f'Reservar Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.hold.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_quant_id': self.id,
                'default_lot_id': self.lot_id.id,
            }
        }
    
    def action_ver_hold(self):
        """Ver detalles del hold activo"""
        self.ensure_one()
        
        if not self.x_hold_activo_id:
            raise UserError('Este lote no tiene una reserva activa.')
        
        return {
            'name': f'Reserva del Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.hold',
            'view_mode': 'form',
            'res_id': self.x_hold_activo_id.id,
            'target': 'new',
        }
    
    def action_cancelar_hold(self):
        """Cancelar el hold activo"""
        self.ensure_one()
        
        if not self.x_hold_activo_id:
            raise UserError('Este lote no tiene una reserva activa.')
        
        self.x_hold_activo_id.action_cancelar_hold()
        
        return NotificationBuilder.build_success(
            '¡Éxito!',
            f'Reserva cancelada para el lote {self.lot_id.name}'
        )
    
    # ==================== MÉTODOS DE API (BÁSICOS) ====================
    @api.model
    def get_current_user_info(self):
        """Obtener información del usuario actual"""
        return {
            'id': self.env.user.id,
            'name': self.env.user.name
        }
    
    @api.model
    def sync_cart_to_session(self, items):
        """Sincronizar carrito desde frontend a BD"""
        cart_model = self.env['shopping.cart']
        cart_model.clear_cart()
        
        for item in items:
            cart_model.add_to_cart(
                quant_id=item['id'],
                lot_id=item['lot_id'],
                product_id=item['product_id'],
                quantity=item['quantity'],
                location_name=item['location_name']
            )
        
        return {'success': True}
    
    # AQUÍ ESTABA LA DUPLICACIÓN (ELIMINADA)
    
    # ==================== OVERRIDE CRÍTICO - FILTRADO DE QUANTS (OPTIMIZADO) ====================
    def _gather(self, product_id, location_id, lot_id=None, package_id=None, 
                owner_id=None, strict=False, qty=None):
        """
        Override para filtrar quants con holds antes de asignación FIFO/LIFO.
        OPTIMIZADO: Usa filtrado por conjuntos (Sets) en lugar de bucles for.
        """
        # Llamar al método original para obtener candidatos
        quants = super(StockQuant, self)._gather(
            product_id, location_id, lot_id=lot_id, package_id=package_id,
            owner_id=owner_id, strict=strict, qty=qty
        )
        
        # Si no hay candidatos, retornar inmediatamente
        if not quants:
            return quants

        # Filtrar por holds de manera eficiente
        return self._filter_quants_by_hold(quants)
    
    def _filter_quants_by_hold(self, quants):
        """
        Filtra quants según holds del cliente permitido Y compañía usando Set Operations.
        Performance: O(1) queries vs O(N) queries.
        """
        cliente_permitido_id = self.env.context.get('allowed_partner_id')
        company_id = self.env.context.get('company_id') or self.env.company.id
        
        # Estrategia: Encontrar los "Blockers" (IDs que NO podemos usar) y restarlos.
        
        # 1. Definir dominio para buscar holds ACTIVOS
        domain_blockers = [
            ('quant_id', 'in', quants.ids),
            ('estado', '=', 'activo'),
            ('company_id', '=', company_id) # Solo holds de esta compañía bloquean stock
        ]
        
        # 2. Refinar lógica según cliente
        if cliente_permitido_id:
            # Si hay un cliente permitido, el hold SOLO es un bloqueo si es para OTRO cliente.
            domain_blockers.append(('partner_id', '!=', cliente_permitido_id))
        else:
            # Si no hay cliente permitido, CUALQUIER hold activo es un bloqueo.
            pass
            
        # 3. Ejecutar búsqueda vectorizada (1 sola Query SQL)
        active_holds = self.env['stock.lot.hold'].sudo().search(domain_blockers)
        
        # 4. Obtener IDs de quants bloqueados
        blocked_quant_ids = set(active_holds.mapped('quant_id').ids)
        
        # 5. Si no hay bloqueos, retornar todo el set original
        if not blocked_quant_ids:
            return quants
            
        # 6. Restar los bloqueados del set original (Odoo mantiene orden FIFO/LIFO)
        quants_validos = quants - quants.browse(blocked_quant_ids)
        
        return quants_validos
    
    def _is_quant_available_for_customer(self, quant, customer_id, company_id):
        """
        Mantenido por compatibilidad con UI u otros métodos que verifiquen 1 a 1.
        Ya no es utilizado por _gather para evitar loops.
        """
        # Sin hold → disponible para todos
        if not quant.x_tiene_hold:
            return True
        
        # Con hold → verificar cliente Y compañía
        if quant.x_hold_activo_id:
            # Verificar que el hold sea de la misma compañía
            if quant.x_hold_activo_id.company_id.id != company_id:
                return True  # Hold de otra compañía no aplica
            
            # Hold de la misma compañía → verificar cliente
            hold_partner_id = quant.x_hold_activo_id.partner_id.id
            return hold_partner_id == customer_id
        
        return False
    
    # ==================== MÉTODOS PARA INVENTARIO VISUAL ====================
    
    @api.model
    def get_inventory_grouped_by_product(self, filters=None):
        """
        Obtener inventario agrupado por producto con filtros avanzados
        
        Args:
            filters: dict - Diccionario con filtros aplicados
            
        Returns:
            list: Lista de productos con inventario agrupado
        """
        domain = [('quantity', '>', 0)]
        
        # Aplicar filtros dinámicos
        if filters:
            domain = self._build_filter_domain(domain, filters)
        
        # Buscar quants que cumplan el dominio
        quants = self.search(domain)
        
        # Agrupar por producto y calcular métricas
        products_data = self._group_quants_by_product(quants)
        
        # Convertir a lista y ordenar
        result = list(products_data.values())
        result.sort(key=lambda x: x['product_name'])
        
        return result
    
    def _build_filter_domain(self, domain, filters):
        """
        Construye el dominio de búsqueda según filtros
        
        Args:
            domain: list - Dominio base
            filters: dict - Filtros a aplicar
            
        Returns:
            list: Dominio actualizado
        """
        if filters.get('product_name'):
            search_term = filters['product_name'].strip()
            domain.append('|')
            domain.append(('product_id.name', 'ilike', search_term))
            domain.append(('product_id.default_code', 'ilike', search_term))
        
        if filters.get('almacen_id'):
            try:
                almacen = self.env['stock.warehouse'].browse(int(filters['almacen_id']))
                if almacen.view_location_id:
                    domain.append(('location_id', 'child_of', almacen.view_location_id.id))
            except (ValueError, TypeError):
                pass
        
        if filters.get('ubicacion_id'):
            try:
                domain.append(('location_id', '=', int(filters['ubicacion_id'])))
            except (ValueError, TypeError):
                pass
        
        if filters.get('tipo'):
            domain.append(('x_tipo', '=', filters['tipo']))
        
        if filters.get('categoria_id'):
            try:
                domain.append(('product_id.categ_id', 'child_of', int(filters['categoria_id'])))
            except (ValueError, TypeError):
                pass
        
        if filters.get('grupo'):
            domain.append(('x_grupo', '=', filters['grupo']))
        
        if filters.get('acabado'):
            domain.append(('x_acabado', '=', filters['acabado']))
        
        if filters.get('grosor'):
            domain.append(('x_grosor', '=', filters['grosor']))
        
        if filters.get('numero_serie'):
            domain.append(('lot_id.name', 'ilike', filters['numero_serie']))
        
        if filters.get('bloque'):
            domain.append(('x_bloque', 'ilike', filters['bloque']))
        
        if filters.get('pedimento'):
            domain.append(('x_pedimento', 'ilike', filters['pedimento']))
        
        if filters.get('contenedor'):
            domain.append(('x_contenedor', 'ilike', filters['contenedor']))
        
        if filters.get('atado'):
            domain.append(('x_atado', 'ilike', filters['atado']))
        
        return domain
    
    def _group_quants_by_product(self, quants):
        """
        Agrupa quants por producto y calcula métricas
        
        Args:
            quants: recordset - Quants a agrupar
            
        Returns:
            defaultdict: Diccionario con productos agrupados
        """
        products_data = defaultdict(lambda: {
            'stock_qty': 0.0,
            'stock_plates': 0,
            'hold_qty': 0.0,
            'hold_plates': 0,
            'committed_qty': 0.0,
            'committed_plates': 0,
            'available_qty': 0.0,
            'available_plates': 0,
            'total_qty': 0.0,
            'quant_ids': [],
            'has_details': False,
            'has_photos': False,
            'plate_area': 0.0,
        })
        
        for quant in quants:
            product = quant.product_id
            key = product.id
            
            # Calcular área de placa
            plate_area = self._calculate_plate_area(quant)
            
            # Verificar hold activo
            hold_activo = self.env['stock.lot.hold'].search([
                ('quant_id', '=', quant.id),
                ('estado', '=', 'activo')
            ], limit=1)
            
            # Calcular cantidades
            metrics = self._calculate_quant_metrics(quant, hold_activo, plate_area)
            
            # Acumular en el producto
            self._accumulate_product_metrics(products_data[key], metrics, quant, product, plate_area)
        
        return products_data
    
    def _calculate_plate_area(self, quant):
        """Calcula el área de una placa"""
        if hasattr(quant, 'x_alto') and hasattr(quant, 'x_ancho'):
            if quant.x_alto and quant.x_ancho:
                try:
                    return float(quant.x_alto) * float(quant.x_ancho)
                except (ValueError, TypeError):
                    pass
        return 0.0
    
    def _calculate_quant_metrics(self, quant, hold_activo, plate_area):
        """
        Calcula métricas individuales de un quant
        
        Args:
            quant: stock.quant record
            hold_activo: stock.lot.hold record or False
            plate_area: float - Área de la placa
            
        Returns:
            dict: Diccionario con métricas calculadas
        """
        total_m2 = quant.quantity
        hold_m2 = total_m2 if hold_activo else 0.0
        committed_m2 = quant.reserved_quantity
        stock_m2 = total_m2
        available_m2 = total_m2 - hold_m2 - committed_m2
        
        total_plates = 0
        hold_plates = 0
        committed_plates = 0
        stock_plates = 0
        available_plates = 0
        
        if plate_area > 0:
            total_plates = int(round(total_m2 / plate_area))
            hold_plates = 1 if hold_activo else 0
            committed_plates = int(round(committed_m2 / plate_area))
            stock_plates = total_plates
            available_plates = stock_plates - hold_plates - committed_plates
        
        return {
            'stock_m2': stock_m2,
            'stock_plates': stock_plates,
            'hold_m2': hold_m2,
            'hold_plates': hold_plates,
            'committed_m2': committed_m2,
            'committed_plates': committed_plates,
            'available_m2': available_m2,
            'available_plates': available_plates,
            'total_m2': total_m2,
        }
    
    def _accumulate_product_metrics(self, product_data, metrics, quant, product, plate_area):
        """
        Acumula métricas en los datos del producto
        
        Args:
            product_data: dict - Datos acumulados del producto
            metrics: dict - Métricas del quant actual
            quant: stock.quant record
            product: product.product record
            plate_area: float - Área de la placa
        """
        # Información básica del producto (solo la primera vez)
        if 'product_id' not in product_data:
            category_name = self._get_category_name(product)
            tipo = self._get_tipo_display(quant)
            
            product_data.update({
                'product_id': product.id,
                'product_name': product.display_name,
                'product_code': product.default_code or '',
                'uom_name': product.uom_id.name,
                'categ_name': category_name,
                'tipo': tipo,
            })
        
        # Acumular métricas
        product_data['stock_qty'] += metrics['stock_m2']
        product_data['stock_plates'] += metrics['stock_plates']
        product_data['hold_qty'] += metrics['hold_m2']
        product_data['hold_plates'] += metrics['hold_plates']
        product_data['committed_qty'] += metrics['committed_m2']
        product_data['committed_plates'] += metrics['committed_plates']
        product_data['available_qty'] += metrics['available_m2']
        product_data['available_plates'] += metrics['available_plates']
        product_data['total_qty'] += metrics['total_m2']
        product_data['quant_ids'].append(quant.id)
        
        # Área de placa (solo la primera vez)
        if plate_area > 0 and product_data['plate_area'] == 0:
            product_data['plate_area'] = plate_area
        
        # Flags de contenido
        if hasattr(quant, 'x_tiene_detalles') and quant.x_tiene_detalles:
            product_data['has_details'] = True
        if hasattr(quant, 'x_cantidad_fotos') and quant.x_cantidad_fotos > 0:
            product_data['has_photos'] = True
    
    def _get_category_name(self, product):
        """Obtiene el nombre de la categoría más específica"""
        if not product.categ_id:
            return ''
        
        current_categ = product.categ_id
        while current_categ.child_id and len(current_categ.child_id) > 0:
            current_categ = current_categ.child_id[0]
        
        return current_categ.name
    
    def _get_tipo_display(self, quant):
        """Obtiene el valor display del campo selection x_tipo"""
        if not hasattr(quant, 'x_tipo') or not quant.x_tipo:
            return ''
        
        selection = quant._fields['x_tipo'].selection
        if callable(selection):
            selection = selection(quant)
        
        return dict(selection).get(quant.x_tipo, '')
    
    @api.model
    def get_quant_details(self, quant_ids):
        """
        Obtener detalles expandidos de quants específicos
        
        Args:
            quant_ids: list - Lista de IDs de quants
            
        Returns:
            list: Lista de diccionarios con detalles de cada quant
        """
        if not quant_ids:
            return []
        
        quants = self.browse(quant_ids)
        details = []
        
        for quant in quants:
            detail = self._build_quant_detail(quant)
            details.append(detail)
        
        return details
    
    def _build_quant_detail(self, quant):
        """
        Construye el diccionario de detalles de un quant
        
        Args:
            quant: stock.quant record
            
        Returns:
            dict: Diccionario con todos los detalles del quant
        """
        # Campos básicos
        color = getattr(quant, 'x_color', None) or ''
        grosor = getattr(quant, 'x_grosor', None) or ''
        alto = getattr(quant, 'x_alto', None) or ''
        ancho = getattr(quant, 'x_ancho', None) or ''
        bloque = getattr(quant, 'x_bloque', None) or ''
        atado = getattr(quant, 'x_atado', None) or ''
        
        # Tipo (selection field)
        tipo = self._get_tipo_display(quant)
        
        # Campos logísticos
        pedimento = getattr(quant, 'x_pedimento', None) or ''
        contenedor = getattr(quant, 'x_contenedor', None) or ''
        referencia_proveedor = getattr(quant, 'x_referencia_proveedor', None) or ''
        
        # Calcular área y placas
        plate_area = self._calculate_plate_area(quant)
        plates_info = self._calculate_plates_info(quant, plate_area)
        
        # Estados
        states = self._get_quant_states(quant)
        
        # Hold info
        hold_info = self._get_hold_info(quant)
        
        # Fotos y detalles
        content_info = self._get_content_info(quant)
        
        # Sales person
        sales_person = self._get_sales_person(quant)
        
        return {
            'id': quant.id,
            'location_name': quant.location_id.complete_name,
            'lot_name': quant.lot_id.name if quant.lot_id else '',
            'quantity': quant.quantity,
            'reserved_quantity': quant.reserved_quantity,
            'available_quantity': quant.quantity - quant.reserved_quantity,
            'total_plates': plates_info['total_plates'],
            'committed_plates': plates_info['committed_plates'],
            'available_plates': plates_info['available_plates'],
            'color': color,
            'grosor': grosor,
            'alto': alto,
            'ancho': ancho,
            'bloque': bloque,
            'atado': atado,
            'tipo': tipo,
            'pedimento': pedimento,
            'contenedor': contenedor,
            'referencia_proveedor': referencia_proveedor,
            'esta_reservado': states['esta_reservado'],
            'en_orden_entrega': states['en_orden_entrega'],
            'en_orden_venta': states['en_orden_venta'],
            'sale_order_ids': states['sale_order_ids'],
            'tiene_detalles': content_info['tiene_detalles'],
            'tiene_hold': hold_info['tiene_hold'],
            'hold_info': hold_info['hold_data'],
            'cantidad_fotos': content_info['cantidad_fotos'],
            'detalles_placa': content_info['detalles_placa'],
            'sales_person': sales_person,
        }
    
    def _calculate_plates_info(self, quant, plate_area):
        """Calcula información de placas"""
        total_plates = 0
        committed_plates = 0
        available_plates = 0
        
        if plate_area > 0:
            total_plates = int(round(quant.quantity / plate_area))
            committed_plates = int(round(quant.reserved_quantity / plate_area))
            available_plates = total_plates - committed_plates
        
        return {
            'total_plates': total_plates,
            'committed_plates': committed_plates,
            'available_plates': available_plates,
        }
    
    def _get_quant_states(self, quant):
        """Obtiene estados del quant (reservas, órdenes, etc)"""
        esta_reservado = quant.reserved_quantity > 0
        
        # Verificar orden de entrega
        en_orden_entrega = False
        if quant.lot_id:
            delivery_moves = self.env['stock.move.line'].search([
                ('lot_id', '=', quant.lot_id.id),
                ('state', 'in', ['assigned', 'done']),
                ('picking_id.picking_type_id.code', '=', 'outgoing')
            ], limit=1)
            en_orden_entrega = bool(delivery_moves)
        
        # Verificar órdenes de venta
        en_orden_venta = False
        sale_order_ids = []
        if quant.lot_id:
            sale_moves = self.env['stock.move.line'].search([
                ('lot_id', '=', quant.lot_id.id),
                ('state', 'in', ['assigned', 'partially_available', 'done']),
                ('move_id.sale_line_id', '!=', False)
            ])
            
            if sale_moves:
                en_orden_venta = True
                for move in sale_moves:
                    if move.move_id.sale_line_id and move.move_id.sale_line_id.order_id:
                        so = move.move_id.sale_line_id.order_id
                        if so.id not in sale_order_ids:
                            sale_order_ids.append(so.id)
        
        return {
            'esta_reservado': esta_reservado,
            'en_orden_entrega': en_orden_entrega,
            'en_orden_venta': en_orden_venta,
            'sale_order_ids': sale_order_ids,
        }
    
    def _get_hold_info(self, quant):
        """Obtiene información de hold activo"""
        tiene_hold = False
        hold_data = {}
        
        if quant.lot_id:
            hold = self.env['stock.lot.hold'].search([
                ('quant_id', '=', quant.id),
                ('estado', '=', 'activo')
            ], limit=1)
            
            if hold:
                tiene_hold = True
                
                proyecto_nombre = ''
                if hasattr(hold, 'project_id') and hold.project_id:
                    proyecto_nombre = hold.project_id.name
                
                arquitecto_nombre = ''
                if hasattr(hold, 'arquitecto_id') and hold.arquitecto_id:
                    arquitecto_nombre = hold.arquitecto_id.name
                
                vendedor_nombre = ''
                if hasattr(hold, 'user_id') and hold.user_id:
                    vendedor_nombre = hold.user_id.name
                
                hold_data = {
                    'id': hold.id,
                    'partner_name': hold.partner_id.name,
                    'fecha_inicio': hold.fecha_inicio.strftime('%d/%m/%Y %H:%M') if hold.fecha_inicio else '',
                    'fecha_expiracion': hold.fecha_expiracion.strftime('%d/%m/%Y %H:%M') if hold.fecha_expiracion else '',
                    'notas': hold.notas or '',
                    'proyecto_nombre': proyecto_nombre,
                    'arquitecto_nombre': arquitecto_nombre,
                    'vendedor_nombre': vendedor_nombre,
                }
        
        return {
            'tiene_hold': tiene_hold,
            'hold_data': hold_data,
        }
    
    def _get_content_info(self, quant):
        """Obtiene información de contenido (fotos, notas)"""
        tiene_detalles = getattr(quant, 'x_tiene_detalles', False) or False
        
        cantidad_fotos = 0
        if quant.lot_id:
            fotos = self.env['stock.lot.image'].search_count([
                ('lot_id', '=', quant.lot_id.id)
            ])
            cantidad_fotos = fotos
        
        detalles_placa = ''
        if quant.lot_id and hasattr(quant.lot_id, 'x_detalles_placa'):
            detalles_placa = quant.lot_id.x_detalles_placa or ''
        
        return {
            'tiene_detalles': tiene_detalles,
            'cantidad_fotos': cantidad_fotos,
            'detalles_placa': detalles_placa,
        }
    
    def _get_sales_person(self, quant):
        """Obtiene información del vendedor"""
        sales_person = ''
        if quant.lot_id and hasattr(quant.lot_id, 'x_sales_person_id'):
            if quant.lot_id.x_sales_person_id:
                sales_person = quant.lot_id.x_sales_person_id.name
        return sales_person
    
    # ==================== MÉTODOS DE FOTOGRAFÍAS ====================
    
    @api.model
    def get_lot_photos(self, quant_id=None):
        """
        Obtener fotografías de un lote
        
        Args:
            quant_id: int - ID del quant
            
        Returns:
            dict: Información del lote y sus fotografías
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            photos = self.env['stock.lot.image'].search([
                ('lot_id', '=', quant.lot_id.id)
            ], order='sequence, id')
            
            photos_data = []
            for photo in photos:
                photos_data.append({
                    'id': photo.id,
                    'name': photo.name,
                    'image': photo.image,
                    'sequence': photo.sequence,
                    'notas': photo.notas or '',
                    'fecha_captura': photo.fecha_captura.strftime('%d/%m/%Y %H:%M') if photo.fecha_captura else '',
                })
            
            result = {
                'lot_id': quant.lot_id.id,
                'lot_name': quant.lot_id.name,
                'product_name': quant.product_id.name,
                'photos': photos_data,
            }
            
            return result
            
        except Exception as e:
            return {'error': f'Error interno: {str(e)}'}
    
    @api.model
    def save_lot_photo(self, quant_id=None, photo_name='', photo_data='', sequence=10, notas=''):
        """
        Guardar una nueva fotografía en un lote
        
        Args:
            quant_id: int - ID del quant
            photo_name: str - Nombre de la foto
            photo_data: str - Datos base64 de la imagen
            sequence: int - Orden de la foto
            notas: str - Notas adicionales
            
        Returns:
            dict: Resultado de la operación
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            photo = self.env['stock.lot.image'].create({
                'lot_id': quant.lot_id.id,
                'name': photo_name,
                'image': photo_data,
                'sequence': sequence,
                'notas': notas,
            })
            
            return {
                'success': True,
                'photo_id': photo.id,
                'message': f'Foto agregada correctamente al lote {quant.lot_id.name}'
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    @api.model
    def delete_lot_photo(self, photo_id):
        """
        Eliminar una fotografía
        
        Args:
            photo_id: int - ID de la foto a eliminar
            
        Returns:
            dict: Resultado de la operación
        """
        try:
            photo = self.env['stock.lot.image'].browse(photo_id)
            
            if not photo.exists():
                return {'error': 'Foto no encontrada'}
            
            photo.unlink()
            
            return {
                'success': True,
                'message': 'Foto eliminada correctamente'
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    # ==================== MÉTODOS DE NOTAS ====================
    
    @api.model
    def get_lot_notes(self, quant_id=None):
        """
        Obtener notas de un lote
        
        Args:
            quant_id: int - ID del quant
            
        Returns:
            dict: Información del lote y sus notas
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            notes = quant.lot_id.x_detalles_placa or ''
            
            result = {
                'lot_id': quant.lot_id.id,
                'lot_name': quant.lot_id.name,
                'product_name': quant.product_id.name,
                'notes': notes,
            }
            
            return result
            
        except Exception as e:
            return {'error': f'Error interno: {str(e)}'}
    
    @api.model
    def save_lot_notes(self, quant_id=None, notes=''):
        """
        Guardar notas de un lote
        
        Args:
            quant_id: int - ID del quant
            notes: str - Notas a guardar
            
        Returns:
            dict: Resultado de la operación
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            quant.lot_id.write({
                'x_detalles_placa': notes
            })
            
            return {
                'success': True,
                'message': f'Notas guardadas correctamente para el lote {quant.lot_id.name}'
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    # ==================== MÉTODOS DE HISTORIAL ====================
    
    @api.model
    def get_lot_history(self, quant_id=None):
        """
        Obtener historial completo de un lote
        
        Args:
            quant_id: int - ID del quant
            
        Returns:
            dict: Información histórica completa del lote
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            lot = quant.lot_id
            
            # Información general
            general_info = self._build_general_info(quant, lot)
            
            # Información de compras
            purchase_info = self._get_purchase_info(lot)
            
            # Movimientos
            movements = self._get_movements(lot)
            
            # Órdenes de venta
            sales_orders = self._get_sales_orders(lot)
            
            # Reservas y apartados
            reservations = self._get_reservations(quant, lot)
            
            # Entregas
            deliveries = self._get_deliveries(lot)
            
            # Estadísticas
            statistics = self._calculate_statistics(movements, sales_orders, reservations, deliveries, lot)
            
            result = {
                'general_info': general_info,
                'purchase_info': purchase_info,
                'movements': movements,
                'sales_orders': sales_orders,
                'reservations': reservations,
                'deliveries': deliveries,
                'statistics': statistics,
            }
            
            return result
            
        except Exception as e:
            return {'error': f'Error interno: {str(e)}'}
    
    def _build_general_info(self, quant, lot):
        """Construye información general del lote"""
        estado_actual = 'Disponible'
        
        if quant.reserved_quantity > 0:
            estado_actual = 'Reservado'
        
        hold_activo = self.env['stock.lot.hold'].search([
            ('quant_id', '=', quant.id),
            ('estado', '=', 'activo')
        ], limit=1)
        
        if hold_activo:
            estado_actual = 'Apartado (Hold)'
        
        return {
            'lot_name': lot.name,
            'product_name': quant.product_id.name,
            'product_code': quant.product_id.default_code or '',
            'fecha_creacion': lot.create_date.strftime('%d/%m/%Y %H:%M') if lot.create_date else '',
            'estado_actual': estado_actual,
            'cantidad_actual': quant.quantity,
            'cantidad_reservada': quant.reserved_quantity,
            'cantidad_disponible': quant.quantity - quant.reserved_quantity,
            'ubicacion_actual': quant.location_id.complete_name,
        }
    
    def _get_purchase_info(self, lot):
        """Obtiene información de compras del lote"""
        purchase_info = []
        
        incoming_moves = self.env['stock.move.line'].search([
            ('lot_id', '=', lot.id),
            ('picking_id.picking_type_id.code', '=', 'incoming')
        ])
        
        po_line_ids = set()
        for move_line in incoming_moves:
            if move_line.move_id and move_line.move_id.purchase_line_id:
                po_line_ids.add(move_line.move_id.purchase_line_id.id)
        
        if po_line_ids:
            purchase_lines = self.env['purchase.order.line'].browse(list(po_line_ids))
            valid_lines = [pl for pl in purchase_lines if pl.order_id and pl.order_id.state in ['purchase', 'done']]
            valid_lines.sort(key=lambda x: x.order_id.date_order if x.order_id.date_order else fields.Datetime.now(), reverse=True)
            
            for po_line in valid_lines[:5]:
                purchase_info.append({
                    'orden_compra': po_line.order_id.name,
                    'proveedor': po_line.order_id.partner_id.name,
                    'fecha_orden': po_line.order_id.date_order.strftime('%d/%m/%Y') if po_line.order_id.date_order else '',
                    'cantidad': po_line.product_qty,
                    'precio_unitario': po_line.price_unit,
                    'total': po_line.price_subtotal,
                    'moneda': po_line.order_id.currency_id.symbol,
                    'estado': dict(po_line.order_id._fields['state'].selection).get(po_line.order_id.state),
                })
        
        return purchase_info
    
    def _get_movements(self, lot):
        """Obtiene movimientos del lote"""
        movements = []
        
        stock_moves = self.env['stock.move.line'].search([
            ('lot_id', '=', lot.id)
        ], order='date desc', limit=50)
        
        for move in stock_moves:
            movement_type = 'Otro'
            icon = 'fa-exchange'
            color = 'secondary'
            
            if move.picking_id:
                picking_code = move.picking_id.picking_type_id.code
                if picking_code == 'incoming':
                    movement_type = 'Entrada'
                    icon = 'fa-arrow-down'
                    color = 'success'
                elif picking_code == 'outgoing':
                    movement_type = 'Salida'
                    icon = 'fa-arrow-up'
                    color = 'danger'
                elif picking_code == 'internal':
                    movement_type = 'Movimiento Interno'
                    icon = 'fa-exchange'
                    color = 'info'
            
            movements.append({
                'fecha': move.date.strftime('%d/%m/%Y %H:%M') if move.date else '',
                'tipo': movement_type,
                'icon': icon,
                'color': color,
                'origen': move.location_id.name,
                'destino': move.location_dest_id.name,
                'cantidad': move.qty_done,
                'referencia': move.picking_id.name if move.picking_id else move.reference or '-',
                'usuario': move.create_uid.name if move.create_uid else '-',
            })
        
        return movements
    
    def _get_sales_orders(self, lot):
        """Obtiene órdenes de venta del lote"""
        sales_orders = []
        
        outgoing_moves = self.env['stock.move.line'].search([
            ('lot_id', '=', lot.id),
            ('picking_id.picking_type_id.code', '=', 'outgoing')
        ])
        
        so_line_ids = set()
        for move_line in outgoing_moves:
            if move_line.move_id and move_line.move_id.sale_line_id:
                so_line_ids.add(move_line.move_id.sale_line_id.id)
        
        if so_line_ids:
            sale_lines = self.env['sale.order.line'].browse(list(so_line_ids))
            valid_lines = [sl for sl in sale_lines if sl.order_id and sl.order_id.state in ['sale', 'done']]
            valid_lines.sort(key=lambda x: x.order_id.date_order if x.order_id.date_order else fields.Datetime.now(), reverse=True)
            
            for so_line in valid_lines[:10]:
                sales_orders.append({
                    'orden_venta': so_line.order_id.name,
                    'cliente': so_line.order_id.partner_id.name,
                    'vendedor': so_line.order_id.user_id.name if so_line.order_id.user_id else '-',
                    'fecha_orden': so_line.order_id.date_order.strftime('%d/%m/%Y') if so_line.order_id.date_order else '',
                    'cantidad': so_line.product_uom_qty,
                    'precio_unitario': so_line.price_unit,
                    'total': so_line.price_subtotal,
                    'moneda': so_line.order_id.currency_id.symbol,
                    'estado': dict(so_line.order_id._fields['state'].selection).get(so_line.order_id.state),
                })
        
        return sales_orders
    
    def _get_reservations(self, quant, lot):
        """Obtiene reservas y apartados del lote"""
        reservations = []
        
        # Holds manuales
        holds = self.env['stock.lot.hold'].search([
            ('quant_id', '=', quant.id)
        ], order='fecha_inicio desc')
        
        for hold in holds:
            reservations.append({
                'tipo': 'Apartado (Hold)',
                'partner': hold.partner_id.name,
                'fecha_inicio': hold.fecha_inicio.strftime('%d/%m/%Y %H:%M') if hold.fecha_inicio else '',
                'fecha_expiracion': hold.fecha_expiracion.strftime('%d/%m/%Y %H:%M') if hold.fecha_expiracion else '',
                'estado': 'Activo' if hold.estado == 'activo' else 'Liberado',
                'notas': hold.notas or '',
                'color': 'warning' if hold.estado == 'activo' else 'secondary'
            })
        
        # Reservas del sistema
        reserved_move_lines = self.env['stock.move.line'].search([
            ('product_id', '=', quant.product_id.id),
            ('lot_id', '=', lot.id),
            ('state', 'in', ['assigned', 'partially_available']),
            ('quantity', '>', 0)
        ])
        
        for move_line in reserved_move_lines:
            partner_name = '-'
            move = move_line.move_id
            
            if move:
                if move.sale_line_id and move.sale_line_id.order_id:
                    partner_name = move.sale_line_id.order_id.partner_id.name
                elif move.picking_id and move.picking_id.partner_id:
                    partner_name = move.picking_id.partner_id.name
            
            reservations.append({
                'tipo': 'Reserva de Stock',
                'partner': partner_name,
                'fecha_inicio': move_line.date.strftime('%d/%m/%Y %H:%M') if move_line.date else '',
                'fecha_expiracion': '-',
                'estado': 'Activo',
                'notas': move_line.picking_id.name if move_line.picking_id else move_line.reference or '',
                'color': 'info'
            })
        
        return reservations
    
    def _get_deliveries(self, lot):
        """Obtiene entregas del lote"""
        deliveries = []
        
        delivery_moves = self.env['stock.move.line'].search([
            ('lot_id', '=', lot.id),
            ('picking_id.picking_type_id.code', '=', 'outgoing')
        ], order='date desc')
        
        for move in delivery_moves:
            picking = move.picking_id
            if picking:
                deliveries.append({
                    'referencia': picking.name,
                    'cliente': picking.partner_id.name if picking.partner_id else '-',
                    'fecha_programada': picking.scheduled_date.strftime('%d/%m/%Y') if picking.scheduled_date else '',
                    'fecha_efectiva': picking.date_done.strftime('%d/%m/%Y %H:%M') if picking.date_done else '-',
                    'cantidad': move.qty_done,
                    'estado': dict(picking._fields['state'].selection).get(picking.state),
                    'origen': picking.origin or '-',
                    'color': 'success' if picking.state == 'done' else 'warning' if picking.state == 'assigned' else 'secondary'
                })
        
        return deliveries
    
    def _calculate_statistics(self, movements, sales_orders, reservations, deliveries, lot):
        """Calcula estadísticas del lote"""
        dias_en_inventario = 0
        if lot.create_date:
            dias_en_inventario = (fields.Datetime.now() - lot.create_date).days
        
        return {
            'total_movimientos': len(movements),
            'total_entradas': len([m for m in movements if m['tipo'] == 'Entrada']),
            'total_salidas': len([m for m in movements if m['tipo'] == 'Salida']),
            'total_ventas': len(sales_orders),
            'total_apartados': len(reservations),
            'total_entregas': len(deliveries),
            'dias_en_inventario': dias_en_inventario,
        }
    
    # ==================== MÉTODOS DE ÓRDENES DE VENTA ====================
    
    @api.model
    def get_sale_order_info(self, sale_order_ids=None):
        """
        Obtener información de órdenes de venta
        
        Args:
            sale_order_ids: list - Lista de IDs de órdenes de venta
            
        Returns:
            dict: Información de las órdenes de venta
        """
        if not sale_order_ids:
            return {'error': 'IDs de órdenes de venta inválidos'}
        
        try:
            sale_orders = self.env['sale.order'].browse(sale_order_ids)
            orders_data = []
            
            for so in sale_orders:
                if not so.exists():
                    continue
                
                orders_data.append({
                    'id': so.id,
                    'name': so.name,
                    'partner_name': so.partner_id.name,
                    'partner_id': so.partner_id.id,
                    'date_order': so.date_order.strftime('%d/%m/%Y') if so.date_order else '',
                    'amount_total': so.amount_total,
                    'currency_symbol': so.currency_id.symbol,
                    'state': so.state,
                    'state_display': dict(so._fields['state'].selection).get(so.state),
                    'user_name': so.user_id.name if so.user_id else '',
                    'commitment_date': so.commitment_date.strftime('%d/%m/%Y') if so.commitment_date else '',
                })
            
            result = {
                'orders': orders_data,
                'count': len(orders_data),
            }
            
            return result
            
        except Exception as e:
            return {'error': f'Error interno: {str(e)}'}
    
    # ==================== MÉTODOS DE HOLD AVANZADOS ====================
    
    @api.model
    def create_lot_hold(self, quant_id=None, partner_id=None, notas=''):
        """
        Crear un hold básico (versión simple)
        
        Args:
            quant_id: int - ID del quant
            partner_id: int - ID del cliente
            notas: str - Notas adicionales
            
        Returns:
            dict: Resultado de la operación
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        if not partner_id:
            return {'error': 'Debe seleccionar un cliente'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            hold_existente = self.env['stock.lot.hold'].search([
                ('quant_id', '=', quant.id),
                ('estado', '=', 'activo')
            ], limit=1)
            
            if hold_existente:
                return {
                    'error': f'Este lote ya tiene una reserva activa para {hold_existente.partner_id.name}'
                }
            
            hold = self.env['stock.lot.hold'].create({
                'lot_id': quant.lot_id.id,
                'quant_id': quant.id,
                'partner_id': partner_id,
                'notas': notas or '',
            })
            
            return {
                'success': True,
                'hold_id': hold.id,
                'message': f'Lote {quant.lot_id.name} apartado para {hold.partner_id.name} hasta {hold.fecha_expiracion.strftime("%d/%m/%Y")}'
            }
            
        except Exception as e:
            return {'error': f'Error al crear apartado: {str(e)}'}
    
    @api.model
    def create_lot_hold_enhanced(self, quant_id=None, partner_id=None, project_id=None, 
                                architect_id=None, notas='', currency_code='USD', 
                                product_prices=None):
        """
        Crear un hold completo con toda la información (versión avanzada)
        
        Args:
            quant_id: int - ID del quant
            partner_id: int - ID del cliente
            project_id: int - ID del proyecto
            architect_id: int - ID del arquitecto
            notas: str - Notas adicionales
            currency_code: str - Código de divisa
            product_prices: dict - Precios de productos
            
        Returns:
            dict: Resultado de la operación
        """
        if isinstance(quant_id, list):
            quant_id = quant_id[0] if quant_id else False
        
        if not quant_id:
            return {'error': 'ID de quant inválido'}
        
        if not partner_id:
            return {'error': 'Debe seleccionar un cliente'}
        
        if not project_id:
            return {'error': 'Debe seleccionar un proyecto'}
        
        if not architect_id:
            return {'error': 'Debe seleccionar un arquitecto'}
        
        try:
            quant = self.browse(quant_id)
            
            if not quant.exists():
                return {'error': 'Quant no encontrado'}
            
            if not quant.lot_id:
                return {'error': 'Este quant no tiene un lote asignado'}
            
            # Verificar hold existente
            hold_existente = self.env['stock.lot.hold'].search([
                ('quant_id', '=', quant.id),
                ('estado', '=', 'activo')
            ], limit=1)
            
            if hold_existente:
                return {
                    'error': f'Este lote ya tiene una reserva activa para {hold_existente.partner_id.name}'
                }
            
            # Calcular fecha de expiración (5 días hábiles)
            from datetime import timedelta
            fecha_inicio = fields.Datetime.now()
            fecha_actual = fecha_inicio
            dias_agregados = 0
            
            while dias_agregados < 5:
                fecha_actual += timedelta(days=1)
                if fecha_actual.weekday() < 5:  # Lunes a viernes
                    dias_agregados += 1
            
            # Agregar información de precios a las notas
            notes_with_prices = notas or ''
            if product_prices:
                notes_with_prices += f'\n\n=== PRECIOS ({currency_code}) ===\n'
                for product_id_str, price in product_prices.items():
                    try:
                        product = self.env['product.product'].browse(int(product_id_str))
                        if product.exists():
                            notes_with_prices += f'• {product.display_name}: {price:.2f} {currency_code}/m²\n'
                    except Exception as e:
                        _logger.warning(f"Error agregando precio para producto {product_id_str}: {str(e)}")
            
            # Crear el hold
            hold = self.env['stock.lot.hold'].create({
                'lot_id': quant.lot_id.id,
                'quant_id': quant.id,
                'partner_id': partner_id,
                'user_id': self.env.user.id,
                'project_id': project_id,
                'arquitecto_id': architect_id,
                'fecha_inicio': fecha_inicio,
                'fecha_expiracion': fecha_actual,
                'notas': notes_with_prices,
            })
            
            partner = self.env['res.partner'].browse(partner_id)
            
            return {
                'success': True,
                'hold_id': hold.id,
                'message': f'Lote {quant.lot_id.name} apartado para {partner.name} hasta {hold.fecha_expiracion.strftime("%d/%m/%Y %H:%M")}'
            }
            
        except Exception as e:
            return {'error': f'Error al crear apartado: {str(e)}'}
    
    
    

    @api.model
    def create_holds_from_cart(self, partner_id=None, project_id=None, 
                            architect_id=None, selected_lots=None, 
                            notes=None, currency_code='USD', 
                            product_prices=None):
        """
        Crear holds múltiples desde el carrito con información de precios
        
        Args:
            partner_id: int - ID del cliente
            project_id: int - ID del proyecto
            architect_id: int - ID del arquitecto
            selected_lots: list - Lista de IDs de quants
            notes: str - Notas adicionales
            currency_code: str - Código de divisa (USD/MXN)
            product_prices: dict - Precios por producto
            
        Returns:
            dict: Resultado con éxitos y errores
        """
        if not partner_id or not selected_lots:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Parámetros inválidos: partner_id o selected_lots'}]
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
                'failed': [{'error': 'Debe seleccionar un arquitecto'}]
            }
        
        # Calcular fecha de expiración (5 días hábiles)
        from datetime import timedelta
        fecha_inicio = fields.Datetime.now()
        fecha_actual = fecha_inicio
        dias_agregados = 0
        
        while dias_agregados < 5:
            fecha_actual += timedelta(days=1)
            if fecha_actual.weekday() < 5:  # Lunes a viernes
                dias_agregados += 1
        
        fecha_expiracion = fecha_actual
        
        # Preparar notas con información de precios
        notes_with_prices = notas or ''
        if product_prices:
            notes_with_prices += f'\n\n=== PRECIOS ({currency_code}) ===\n'
            for product_id_str, price in product_prices.items():
                try:
                    product = self.env['product.product'].browse(int(product_id_str))
                    if product.exists():
                        notes_with_prices += f'• {product.display_name}: {price:.2f} {currency_code}/m²\n'
                except Exception as e:
                    _logger.warning(f"Error agregando precio para producto {product_id_str}: {str(e)}")
        
        # Crear holds
        holds_created = []
        errors = []
        
        for quant_id in selected_lots:
            try:
                quant = self.browse(quant_id)
                
                if not quant.exists():
                    errors.append({
                        'quant_id': quant_id,
                        'error': 'Quant no encontrado'
                    })
                    continue
                
                if not quant.lot_id:
                    errors.append({
                        'quant_id': quant_id,
                        'error': 'Quant sin lote asignado'
                    })
                    continue
                
                # Verificar si ya tiene hold
                if quant.x_tiene_hold:
                    errors.append({
                        'lot_name': quant.lot_id.name,
                        'error': f'Ya apartado para {quant.x_hold_para}'
                    })
                    continue
                
                # Crear el hold
                hold = self.env['stock.lot.hold'].create({
                    'lot_id': quant.lot_id.id,
                    'quant_id': quant.id,
                    'partner_id': partner_id,
                    'user_id': self.env.user.id,
                    'project_id': project_id,
                    'arquitecto_id': architect_id,
                    'fecha_inicio': fecha_inicio,
                    'fecha_expiracion': fecha_expiracion,
                    'notas': notes_with_prices,
                })
                
                holds_created.append({
                    'lot_name': quant.lot_id.name,
                    'hold_id': hold.id,
                    'expira': hold.fecha_expiracion.strftime('%d/%m/%Y %H:%M')
                })
                
            except Exception as e:
                errors.append({
                    'lot_name': quant.lot_id.name if quant.exists() and quant.lot_id else 'Desconocido',
                    'error': str(e)
                })
        
        # Limpiar carrito si hubo éxitos
        if holds_created:
            try:
                self.env['shopping.cart'].clear_cart()
            except Exception as e:
                _logger.warning(f"Error al limpiar carrito: {str(e)}")
        
        return {
            'success': len(holds_created),
            'errors': len(errors),
            'holds': holds_created,
            'failed': errors
        }

    # ==================== MÉTODOS DE BÚSQUEDA AUXILIARES ====================
    
    @api.model
    def search_partners(self, name=''):
        """
        Buscar partners (clientes)
        
        Args:
            name: str - Término de búsqueda
            
        Returns:
            list: Lista de partners encontrados
        """
        if not name or name.strip() == '':
            domain = [
                ('active', '=', True),
                '|', '|',
                ('customer_rank', '>', 0),
                ('supplier_rank', '>', 0),
                ('is_company', '=', True)
            ]
        else:
            search_term = name.strip()
            domain = [
                ('active', '=', True),
                '|', '|', '|', '|',
                ('name', 'ilike', search_term),
                ('ref', 'ilike', search_term),
                ('vat', 'ilike', search_term),
                ('email', 'ilike', search_term),
                ('phone', 'ilike', search_term)
            ]
        
        partners = self.env['res.partner'].search(domain, limit=50, order='name')
        
        result = []
        for partner in partners:
            display_parts = [partner.name]
            if partner.ref:
                display_parts.append(f"[{partner.ref}]")
            if partner.vat:
                display_parts.append(f"RFC: {partner.vat}")
            
            display_name = ' '.join(display_parts)
            
            result.append({
                'id': partner.id,
                'name': partner.name,
                'ref': partner.ref or '',
                'vat': partner.vat or '',
                'display_name': display_name
            })
        
        return result
    
    @api.model
    def get_projects(self, search_term=''):
        """Buscar proyectos de mármol"""
        domain = [('x_es_proyecto_marmol', '=', True)]
        
        if search_term:
            domain.append(('name', 'ilike', search_term))
        
        projects = self.env['project.project'].search(domain, limit=50, order='name')
        
        result = []
        for project in projects:
            result.append({
                'id': project.id,
                'name': project.name,
            })
        
        return result
    
    @api.model
    def get_architects(self, search_term=''):
        """Buscar arquitectos"""
        domain = [('x_es_arquitecto', '=', True)]
        
        if search_term:
            domain.append(('name', 'ilike', search_term))
        
        architects = self.env['res.partner'].search(domain, limit=50, order='name')
        
        result = []
        for architect in architects:
            display_parts = [architect.name]
            if architect.ref:
                display_parts.append(f"[{architect.ref}]")
            if architect.vat:
                display_parts.append(f"RFC: {architect.vat}")
            
            display_name = ' '.join(display_parts)
            
            result.append({
                'id': architect.id,
                'name': architect.name,
                'ref': architect.ref or '',
                'vat': architect.vat or '',
                'display_name': display_name
            })
        
        return result
    
    # ==================== MÉTODOS DE CREACIÓN AUXILIARES ====================
    
    @api.model
    def create_partner(self, name, vat='', ref=''):
        """Crear un nuevo cliente"""
        try:
            partner = self.env['res.partner'].create({
                'name': name,
                'vat': vat or False,
                'ref': ref or False,
                'customer_rank': 1,
                'company_type': 'company',
            })
            
            return {
                'success': True,
                'partner_id': partner.id,
                'partner': {
                    'id': partner.id,
                    'name': partner.name,
                    'ref': partner.ref or '',
                    'vat': partner.vat or '',
                    'display_name': partner.name
                }
            }
        except Exception as e:
            return {'error': str(e)}
    
    @api.model
    def create_project(self, name):
        """Crear un nuevo proyecto"""
        try:
            project = self.env['project.project'].create({
                'name': name,
                'x_es_proyecto_marmol': True,
            })
            
            return {
                'success': True,
                'project_id': project.id,
                'project': {
                    'id': project.id,
                    'name': project.name,
                }
            }
        except Exception as e:
            return {'error': str(e)}
    
    @api.model
    def create_architect(self, name, vat='', ref=''):
        """Crear un nuevo arquitecto"""
        try:
            architect = self.env['res.partner'].create({
                'name': name,
                'vat': vat or False,
                'ref': ref or False,
                'x_es_arquitecto': True,
                'company_type': 'person',
            })
            
            return {
                'success': True,
                'architect_id': architect.id,
                'architect': {
                    'id': architect.id,
                    'name': architect.name,
                    'ref': architect.ref or '',
                    'vat': architect.vat or '',
                    'display_name': architect.name
                }
            }
        except Exception as e:
            return {'error': str(e)}