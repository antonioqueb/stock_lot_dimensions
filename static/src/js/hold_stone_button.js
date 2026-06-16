/** @odoo-module */
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState, onWillStart, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class HoldStoneButton extends Component {
    static template = "stock_lot_dimensions.HoldStoneButton";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this._detailsRow = null;
        this._popupRoot = null;
        this._popupKeyHandler = null;
        this._popupObserver = null;
        // Caché local del desglose de parcialidades por lote (FORMATOS/PIEZAS),
        // espejo de x_lot_breakdown_json. Igual que sale_stone_selection.
        this._localBreakdown = null;

        this.state = useState({
            isExpanded: false,
            selectedCount: 0,
        });

        onWillStart(() => this._updateCount());
        onWillUpdateProps((nextProps) => this._updateCount(nextProps));

        onWillUnmount(() => {
            this.removeDetailsRow();
            this.destroyPopup();
        });
    }

    // ─────────────────────────────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────────────────────────────

    _escapeHtml(value) {
        const raw = value === null || value === undefined ? "" : String(value);
        return raw
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    _fmt(num) {
        const value = parseFloat(num);
        if (Number.isNaN(value)) return "0.00";
        return value.toFixed(2);
    }

    _fmtDim(num) {
        const value = parseFloat(num);
        if (!value || Number.isNaN(value)) return "—";
        return value % 1 === 0 ? value.toFixed(0) : value.toFixed(2);
    }

    _tipoLabel(tipo) {
        const clean = (tipo || "placa").toLowerCase();
        return clean.charAt(0).toUpperCase() + clean.slice(1);
    }

    _qtyLabel(tipo) {
        return (tipo || "").toLowerCase() === "pieza" ? "pzas" : "m²";
    }

    _extractIds(raw) {
        if (!raw) return [];
        if (Array.isArray(raw)) return raw.filter((item) => typeof item === "number");
        if (raw.currentIds) return raw.currentIds;
        if (raw.resIds) return raw.resIds;
        if (raw.records) return raw.records.map((record) => record.resId || record.data?.id).filter(Boolean);
        return [];
    }

    _id(field) {
        if (!field) return 0;
        if (typeof field === "number") return field;
        if (Array.isArray(field)) return field[0] || 0;
        return field.id || 0;
    }

    _name(field) {
        if (!field) return "";
        if (Array.isArray(field)) return field[1] || "";
        return field.display_name || field.name || "";
    }

    getProductId() {
        return this._id(this.props.record.data.product_id);
    }

    getProductName() {
        return this._name(this.props.record.data.product_id);
    }

    getCurrentLotIds() {
        return this._extractIds(this.props.record.data.lot_ids);
    }

    _updateCount(props = this.props) {
        this.state.selectedCount = this._extractIds(props?.record?.data?.lot_ids).length;
    }

    // ─────────────────────────────────────────────────────────────────────
    // Cantidad / m²
    // ─────────────────────────────────────────────────────────────────────

    _hasBreakdownField() {
        return !!(this.props.record.data && "x_lot_breakdown_json" in this.props.record.data);
    }

    _getRecordId() {
        const rec = this.props.record;
        if (rec.resId) return rec.resId;
        if (rec.data && rec.data.id) return rec.data.id;
        return null;
    }

    _getCurrentBreakdownMap() {
        // Desglose por lote de parcialidades (FORMATOS/PIEZAS). Prefiere la caché
        // local; si no, lee del record (acepta objeto o string JSON), igual que
        // sale_stone_selection. Devuelve {lotIdStr: cantidad}.
        let raw = this._localBreakdown;
        if (raw === null || raw === undefined) {
            raw = this.props.record.data.x_lot_breakdown_json;
        }
        if (!raw) return {};
        if (typeof raw === "string") {
            try {
                raw = JSON.parse(raw);
            } catch {
                return {};
            }
        }
        if (typeof raw !== "object") return {};
        const map = {};
        for (const [key, value] of Object.entries(raw)) {
            map[String(key)] = parseFloat(value) || 0;
        }
        return map;
    }

    /**
     * Persiste lot_ids + desglose de inmediato (réplica de
     * sale_stone_selection._commitSelectionToServer): actualiza el record en
     * memoria y, si la línea ya existe en BD, escribe directo por ORM para
     * disparar el write() de Python (sync de cantidades) sin pulsar Guardar.
     */
    async _commitSelectionToServer(newLotIds, breakdown = {}) {
        this._localBreakdown = { ...breakdown };
        const hasField = this._hasBreakdownField();
        const breakdownVal =
            breakdown && Object.keys(breakdown).length ? breakdown : false;

        const m2 = await this._computeM2ForLots(newLotIds, breakdown);
        const vals = { lot_ids: [[6, 0, newLotIds]], cantidad_m2: m2 };
        if (hasField) vals.x_lot_breakdown_json = breakdownVal;
        await this.props.record.update(vals);

        const recordId = this._getRecordId();
        if (recordId && typeof recordId === "number" && recordId > 0) {
            const wvals = { lot_ids: [[6, 0, newLotIds]] };
            if (hasField) wvals.x_lot_breakdown_json = breakdownVal;
            await this.orm.write("stock.lot.hold.order.line", [recordId], wvals);
            await this._refreshCantidadFromServer();
        }

        this._updateCount();
    }

    /**
     * Guarda SOLO el desglose (al editar la parcialidad de un lote) y refresca
     * la cantidad calculada por el backend. Réplica de _saveBreakdownToServer.
     */
    async _saveHoldBreakdownToServer(breakdown) {
        this._localBreakdown = { ...breakdown };
        if (!this._hasBreakdownField()) return;
        const breakdownVal =
            breakdown && Object.keys(breakdown).length ? breakdown : false;

        await this.props.record.update({ x_lot_breakdown_json: breakdownVal });

        const recordId = this._getRecordId();
        if (recordId && typeof recordId === "number" && recordId > 0) {
            try {
                await this.orm.write("stock.lot.hold.order.line", [recordId], {
                    x_lot_breakdown_json: breakdownVal,
                });
                await this._refreshCantidadFromServer();
            } catch (e) {
                console.warn("[HOLD STONE] Error guardando desglose:", e);
            }
        }
    }

    /** Lee cantidad_m2 recalculada por el backend y la refleja en el record. */
    async _refreshCantidadFromServer() {
        const recordId = this._getRecordId();
        if (!recordId || typeof recordId !== "number" || recordId <= 0) return;
        try {
            const rows = await this.orm.read(
                "stock.lot.hold.order.line",
                [recordId],
                ["cantidad_m2"]
            );
            if (rows && rows.length) {
                await this.props.record.update({ cantidad_m2: rows[0].cantidad_m2 || 0 });
            }
        } catch (e) {
            console.warn("[HOLD STONE] No se pudo refrescar cantidad:", e);
        }
    }

    async _computeM2ForLots(lotIds, breakdown = null) {
        if (!lotIds || !lotIds.length) return 0.0;

        try {
            const quants = await this.orm.searchRead(
                "stock.quant",
                [
                    ["lot_id", "in", lotIds],
                    ["location_id.usage", "=", "internal"],
                    ["quantity", ">", 0],
                ],
                ["lot_id", "quantity"],
                { limit: lotIds.length * 3 }
            );

            // Cantidad completa por lote (placas).
            const qtyByLot = {};
            for (const quant of quants) {
                const lid = quant.lot_id ? quant.lot_id[0] : 0;
                qtyByLot[String(lid)] = (qtyByLot[String(lid)] || 0) + (quant.quantity || 0);
            }

            let total = 0.0;
            for (const lid of lotIds) {
                const key = String(lid);
                if (breakdown && breakdown[key] !== undefined) {
                    // Parcialidad seleccionada (formato/pieza).
                    total += parseFloat(breakdown[key]) || 0;
                } else {
                    total += qtyByLot[key] || 0;
                }
            }

            return total;
        } catch (error) {
            console.warn("[HOLD STONE] Error calculando m²:", error);
            return 0.0;
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Toggle principal
    // ─────────────────────────────────────────────────────────────────────

    async handleToggle(ev) {
        ev.stopPropagation();
        ev.preventDefault();

        if (this.state.isExpanded) {
            this.removeDetailsRow();
            this.state.isExpanded = false;
            return;
        }

        document.querySelectorAll(".hold-stone-selected-row").forEach((row) => row.remove());

        const tr = ev.currentTarget.closest("tr");
        if (!tr) return;

        this.state.isExpanded = true;
        await this._injectDetail(tr);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Detalle inline
    // ─────────────────────────────────────────────────────────────────────

    async _injectDetail(row) {
        const newTr = document.createElement("tr");
        newTr.className = "hold-stone-selected-row";

        const td = document.createElement("td");
        td.colSpan = row.querySelectorAll("td").length || 10;
        td.className = "hold-stone-selected-cell";

        const container = document.createElement("div");
        container.className = "hold-stone-selected-container";

        const currentLotIds = this.getCurrentLotIds();

        const header = document.createElement("div");
        header.className = "hold-stone-selected-header";
        const triggerIcon = currentLotIds.length > 0 ? "fa-pencil" : "fa-plus";
        const triggerLabel = currentLotIds.length > 0 ? "Editar" : "Añadir Materiales";
        header.innerHTML = `
            <button class="hold-stone-add-btn hold-stone-add-btn-trigger hold-stone-add-btn-prominent">
                <i class="fa ${triggerIcon} me-1"></i>
                ${triggerLabel}
            </button>

            <span class="hold-stone-selected-title">
                <i class="fa fa-check-circle me-2"></i>
                Placas seleccionadas
                <span class="hold-stone-sel-badge" id="hold-stone-sel-badge">${currentLotIds.length}</span>
            </span>
        `;

        const body = document.createElement("div");
        body.className = "hold-stone-selected-body";

        container.appendChild(header);
        container.appendChild(body);
        td.appendChild(container);
        newTr.appendChild(td);

        row.after(newTr);
        this._detailsRow = newTr;

        await this._renderDetail(body, currentLotIds);

        header.querySelector(".hold-stone-add-btn-trigger").addEventListener("click", (event) => {
            event.stopPropagation();
            event.preventDefault();
            this.openPopup();
        });
    }

    async _renderDetail(container, lotIds) {
        if (!lotIds.length) {
            container.innerHTML = `
                <div class="hold-stone-no-selection">
                    <i class="fa fa-info-circle me-2 text-muted"></i>
                    <span class="text-muted">
                        Sin materiales seleccionados. Usa <strong>Añadir Materiales</strong> para comenzar.
                    </span>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="hold-stone-table-loading">
                <i class="fa fa-circle-o-notch fa-spin me-2"></i>
                Cargando placas seleccionadas...
            </div>
        `;

        try {
            const [lots, quants] = await Promise.all([
                this.orm.searchRead(
                    "stock.lot",
                    [["id", "in", lotIds]],
                    [
                        "name",
                        "x_bloque",
                        "x_atado",
                        "x_alto",
                        "x_ancho",
                        "x_grosor",
                        "x_tipo",
                        "x_color",
                    ],
                    { limit: lotIds.length }
                ),
                this.orm.searchRead(
                    "stock.quant",
                    [
                        ["lot_id", "in", lotIds],
                        ["location_id.usage", "=", "internal"],
                        ["quantity", ">", 0],
                    ],
                    ["lot_id", "quantity"],
                    { limit: lotIds.length * 3 }
                ),
            ]);

            const qtyMap = {};
            for (const quant of quants) {
                const lotId = quant.lot_id?.[0];
                if (!lotId) continue;
                qtyMap[lotId] = (qtyMap[lotId] || 0) + (quant.quantity || 0);
            }

            const lotMap = {};
            for (const lot of lots) {
                lotMap[lot.id] = lot;
            }

            // Desglose de parcialidades guardado (FORMATOS/PIEZAS): la cantidad
            // mostrada debe ser la parcial, no el total del lote.
            const breakdown = this._getCurrentBreakdownMap();

            let total = 0;
            let rows = "";

            for (const lotId of lotIds) {
                const lot = lotMap[lotId];
                if (!lot) continue;

                const key = String(lotId);
                const availQty = qtyMap[lotId] || 0;
                const tipo = (lot.x_tipo || "placa").toLowerCase();
                // FORMATOS/PIEZAS admiten parcialidad editable; PLACAS no.
                const isPartial = tipo === "formato" || tipo === "pieza";
                const qty =
                    isPartial && breakdown[key] !== undefined ? breakdown[key] : availQty;
                const qtyLabel = tipo === "pieza" ? "pzas" : "m²";
                const inputStep = tipo === "pieza" ? "1" : "0.01";

                total += qty;

                const qtyCell = isPartial
                    ? `<input type="number" class="hold-stone-qty-input"
                              data-lot-id="${lotId}" data-max="${availQty}"
                              step="${inputStep}" min="0" max="${availQty}"
                              value="${qty}" style="width: 82px; text-align: right;"/> ${qtyLabel}`
                    : `${this._fmt(qty)} ${qtyLabel}`;

                rows += `
                    <tr data-lot-row="${lotId}">
                        <td class="cell-lot">${this._escapeHtml(lot.name)}</td>
                        <td>${this._escapeHtml(lot.x_bloque || "—")}</td>
                        <td>${this._escapeHtml(lot.x_atado || "—")}</td>
                        <td class="col-num">${this._fmtDim(lot.x_alto)}</td>
                        <td class="col-num">${this._fmtDim(lot.x_ancho)}</td>
                        <td class="col-num">${this._fmtDim(lot.x_grosor)}</td>
                        <td class="col-num text-muted">${this._fmt(availQty)} ${qtyLabel}</td>
                        <td class="col-num fw-semibold col-qty-input">${qtyCell}</td>
                        <td>
                            <span class="hold-stone-tag hold-stone-tag-tipo-${this._escapeHtml(tipo)}">
                                ${this._escapeHtml(this._tipoLabel(tipo))}
                            </span>
                        </td>
                        <td>${this._escapeHtml(lot.x_color || "—")}</td>
                        <td class="col-act">
                            <button class="hold-stone-remove-btn" data-lot-id="${lotId}" title="Quitar placa">
                                <i class="fa fa-times"></i>
                            </button>
                        </td>
                    </tr>
                `;
            }

            container.innerHTML = `
                <table class="hold-stone-sel-table">
                    <thead>
                        <tr>
                            <th>Lote</th>
                            <th>Bloque</th>
                            <th>Atado</th>
                            <th class="col-num">Alto</th>
                            <th class="col-num">Largo</th>
                            <th class="col-num">Espesor</th>
                            <th class="col-num">Disp.</th>
                            <th class="col-num">Cantidad</th>
                            <th>Tipo</th>
                            <th>Color</th>
                            <th class="col-act"></th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                    <tfoot>
                        <tr class="hold-stone-total-row">
                            <td colspan="7" class="text-end fw-bold text-muted">Total:</td>
                            <td id="hold-sel-total" class="col-num fw-bold hold-stone-total-qty">${this._fmt(total)}</td>
                            <td colspan="3"></td>
                        </tr>
                    </tfoot>
                </table>
            `;

            container.querySelectorAll(".hold-stone-remove-btn").forEach((btn) => {
                btn.addEventListener("click", (event) => {
                    event.stopPropagation();
                    event.preventDefault();
                    this._removeLot(parseInt(btn.dataset.lotId, 10));
                });
            });

            // Inputs de parcialidad (FORMATO/PIEZA): guardado con debounce + blur,
            // igual que sale_stone_selection.
            container.querySelectorAll(".hold-stone-qty-input").forEach((input) => {
                let debounceTimer = null;
                input.addEventListener("input", () => {
                    if (debounceTimer) clearTimeout(debounceTimer);
                    debounceTimer = setTimeout(() => this._onHoldQtyInputChange(input), 500);
                });
                input.addEventListener("blur", () => {
                    if (debounceTimer) clearTimeout(debounceTimer);
                    this._onHoldQtyInputChange(input);
                });
            });
        } catch (error) {
            container.innerHTML = `
                <div class="text-danger p-2">
                    <i class="fa fa-exclamation-triangle me-2"></i>
                    Error: ${this._escapeHtml(error.message)}
                </div>
            `;
        }
    }

    async _onHoldQtyInputChange(input) {
        const lotId = parseInt(input.dataset.lotId, 10);
        if (!lotId) return;
        const maxQty = parseFloat(input.dataset.max) || 0;
        let val = parseFloat(input.value) || 0;
        if (val < 0) val = 0;
        if (maxQty && val > maxQty) val = maxQty;
        input.value = val;

        const breakdown = this._getCurrentBreakdownMap();
        if (val > 0) {
            breakdown[String(lotId)] = val;
        } else {
            delete breakdown[String(lotId)];
        }

        await this._saveHoldBreakdownToServer(breakdown);
        this._recalcHoldInlineTotal();
    }

    _recalcHoldInlineTotal() {
        if (!this._detailsRow) return;
        const totalEl = this._detailsRow.querySelector("#hold-sel-total");
        if (!totalEl) return;

        let total = 0;
        this._detailsRow.querySelectorAll("tbody tr td.col-qty-input").forEach((td) => {
            const inp = td.querySelector("input.hold-stone-qty-input");
            if (inp) {
                total += parseFloat(inp.value) || 0;
            } else {
                const m = td.textContent.match(/([\d.]+)/);
                if (m) total += parseFloat(m[1]) || 0;
            }
        });
        totalEl.textContent = this._fmt(total);
    }

    async _removeLot(lotId) {
        const newIds = this.getCurrentLotIds().filter((id) => id !== lotId);
        // Conservar el desglose de los lotes restantes (parcialidades de
        // formatos/piezas); descartar la entrada del lote removido.
        const breakdown = this._getCurrentBreakdownMap();
        delete breakdown[String(lotId)];
        await this._commitSelectionToServer(newIds, breakdown);
        await this._refreshDetail();
    }

    async _refreshDetail() {
        if (!this._detailsRow) return;

        const body = this._detailsRow.querySelector(".hold-stone-selected-body");
        if (!body) return;

        const ids = this.getCurrentLotIds();

        const badge = this._detailsRow.querySelector(".hold-stone-sel-badge");
        if (badge) badge.textContent = ids.length;

        const trigger = this._detailsRow.querySelector(".hold-stone-add-btn-trigger");
        if (trigger) {
            const triggerIcon = ids.length > 0 ? "fa-pencil" : "fa-plus";
            const triggerLabel = ids.length > 0 ? "Editar" : "Añadir Materiales";
            trigger.innerHTML = `<i class="fa ${triggerIcon} me-1"></i> ${triggerLabel}`;
        }

        await this._renderDetail(body, ids);
    }

    removeDetailsRow() {
        if (this._detailsRow) {
            this._detailsRow.remove();
            this._detailsRow = null;
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Popup fullscreen
    // ─────────────────────────────────────────────────────────────────────

    openPopup() {
        this.destroyPopup();

        this._popupRoot = document.createElement("div");
        this._popupRoot.className = "hold-stone-popup-root";
        document.body.appendChild(this._popupRoot);

        this._buildPopup(this.getProductId());
    }

    _buildPopup(fixedProductId) {
        const root = this._popupRoot;
        const PAGE_SIZE = 35;
        const showProductSelector = !fixedProductId;

        const state = {
            quants: [],
            total: 0,
            hasMore: false,
            loading: false,
            loadingMore: false,
            page: 0,
            pending: new Set(this.getCurrentLotIds()),
            // Se siembra con las parcialidades ya guardadas (FORMATOS/PIEZAS) para
            // no perderlas al reabrir el selector. Las PLACAS se completan al
            // cargar sus quants (cantidad completa).
            pendingQtyMap: this._getCurrentBreakdownMap(),
            // lotId(str) -> 'placa' | 'formato' | 'pieza'
            tipoByLot: {},
            filters: {
                lot_name: "",
                bloque: "",
                atado: "",
                alto_min: "",
                ancho_min: "",
                tipo: "",
            },
            productId: fixedProductId,
        };

        let searchTimer = null;

        root.innerHTML = `
            <div class="hold-stone-popup-overlay" id="hold-popup-overlay">
                <div class="hold-stone-popup-container">

                    <div class="hold-stone-popup-header">
                        <div class="hold-stone-popup-title">
                            <i class="fa fa-th me-2"></i>
                            Seleccionar placas
                            <span class="hold-stone-popup-subtitle">
                                ${this.getProductName() ? "— " + this._escapeHtml(this.getProductName()) : ""}
                            </span>
                        </div>

                        <div class="hold-stone-popup-header-actions">
                            <span class="hold-stone-badge-selected">
                                <i class="fa fa-check-circle me-1"></i>
                                <span id="hold-popup-count">${state.pending.size}</span> seleccionadas
                            </span>

                            <span class="hold-stone-badge-qty-total">
                                <i class="fa fa-balance-scale me-1"></i>
                                <span id="hold-popup-qty">0.00</span>
                                <span id="hold-popup-unit">m²</span>
                            </span>

                            <button class="hold-stone-btn hold-stone-btn-accent" id="hold-popup-confirm-top">
                                <i class="fa fa-check me-1"></i>
                                Confirmar
                            </button>

                            <button class="hold-stone-btn hold-stone-btn-ghost" id="hold-popup-close">
                                <i class="fa fa-times"></i>
                            </button>
                        </div>
                    </div>

                    <div class="hold-stone-popup-filters">
                        ${
                            showProductSelector
                                ? `<div class="hold-stone-filter-group">
                                    <label>Producto</label>
                                    <select class="hold-stone-filter-input" id="hold-filter-product" style="width: 260px;">
                                        <option value="">Todos</option>
                                    </select>
                                </div>`
                                : ""
                        }

                        <div class="hold-stone-filter-group">
                            <label>Lote</label>
                            <input type="text" class="hold-stone-filter-input" id="hold-filter-lot" placeholder="Buscar lote..."/>
                        </div>

                        <div class="hold-stone-filter-group">
                            <label>Bloque</label>
                            <input type="text" class="hold-stone-filter-input" id="hold-filter-block" placeholder="Bloque..."/>
                        </div>

                        <div class="hold-stone-filter-group">
                            <label>Atado</label>
                            <input type="text" class="hold-stone-filter-input" id="hold-filter-bundle" placeholder="Atado..."/>
                        </div>

                        <div class="hold-stone-filter-group">
                            <label>Alto mín.</label>
                            <input type="number" class="hold-stone-filter-input hold-stone-filter-sm" id="hold-filter-height" placeholder="0" step="0.01"/>
                        </div>

                        <div class="hold-stone-filter-group">
                            <label>Largo mín.</label>
                            <input type="number" class="hold-stone-filter-input hold-stone-filter-sm" id="hold-filter-width" placeholder="0" step="0.01"/>
                        </div>

                        <div class="hold-stone-filter-group">
                            <label>Tipo</label>
                            <select class="hold-stone-filter-input" id="hold-filter-type">
                                <option value="">Todos</option>
                                <option value="placa">Placa</option>
                                <option value="formato">Formato</option>
                                <option value="pieza">Pieza</option>
                            </select>
                        </div>

                        <div class="hold-stone-filter-actions">
                            <button class="hold-stone-btn hold-stone-btn-select-all" id="hold-popup-select-all">
                                <i class="fa fa-check-square-o me-1"></i>
                                Todo
                            </button>

                            <button class="hold-stone-btn hold-stone-btn-clear-all" id="hold-popup-clear-all">
                                <i class="fa fa-square-o me-1"></i>
                                Limpiar
                            </button>
                        </div>

                        <div class="hold-stone-filter-spacer"></div>

                        <div class="hold-stone-filter-stats">
                            <span id="hold-popup-stat" class="hold-stone-filter-stat-loading">
                                <i class="fa fa-circle-o-notch fa-spin me-1"></i>
                                Buscando...
                            </span>
                        </div>
                    </div>

                    <div class="hold-stone-popup-body" id="hold-popup-body">
                        <div class="hold-stone-empty-state">
                            <i class="fa fa-circle-o-notch fa-spin fa-2x text-muted"></i>
                            <div class="hold-stone-empty-text mt-2">Cargando inventario...</div>
                        </div>
                    </div>

                    <div class="hold-stone-popup-footer">
                        <span class="hold-stone-footer-info" id="hold-popup-footer-info">—</span>

                        <div class="hold-stone-footer-qty-summary">
                            <span id="hold-popup-footer-qty">0.00 m²</span>
                        </div>

                        <div class="hold-stone-footer-actions">
                            <button class="hold-stone-btn hold-stone-btn-outline" id="hold-popup-cancel">
                                Cancelar
                            </button>

                            <button class="hold-stone-btn hold-stone-btn-primary-dark" id="hold-popup-confirm-bottom">
                                <i class="fa fa-check me-1"></i>
                                Agregar selección
                            </button>
                        </div>
                    </div>

                </div>
            </div>
        `;

        const overlay = root.querySelector("#hold-popup-overlay");
        const body = root.querySelector("#hold-popup-body");
        const stat = root.querySelector("#hold-popup-stat");
        const footerInfo = root.querySelector("#hold-popup-footer-info");
        const badgeCount = root.querySelector("#hold-popup-count");
        const badgeQty = root.querySelector("#hold-popup-qty");
        const badgeUnit = root.querySelector("#hold-popup-unit");
        const footerQty = root.querySelector("#hold-popup-footer-qty");
        const productSelect = root.querySelector("#hold-filter-product");

        const getQuantByLotId = (lotId) => {
            return state.quants.find((quant) => quant.lot_id && quant.lot_id[0] === lotId);
        };

        const rememberQuant = (quant) => {
            const lotId = quant.lot_id ? quant.lot_id[0] : 0;
            if (!lotId) return;
            const lotIdStr = String(lotId);
            // Registrar el tipo del lote para decidir si admite parcialidad.
            state.tipoByLot[lotIdStr] = (quant.x_tipo || "placa").toLowerCase();
            // No pisar una parcialidad ya seleccionada (sembrada del desglose o
            // editada por el usuario); solo inicializar con el lote completo.
            if (state.pendingQtyMap[lotIdStr] === undefined) {
                state.pendingQtyMap[lotIdStr] = quant.quantity || 0;
            }
        };

        const getQtyForLot = (lotId) => {
            const lotIdStr = String(lotId);

            if (state.pendingQtyMap[lotIdStr] !== undefined) {
                return parseFloat(state.pendingQtyMap[lotIdStr]) || 0;
            }

            const quant = getQuantByLotId(lotId);
            return quant ? quant.quantity || 0 : 0;
        };

        const computeSelectedTotals = () => {
            let total = 0;
            for (const lotId of state.pending) {
                total += getQtyForLot(lotId);
            }
            return total;
        };

        const updateQtyDisplay = () => {
            const total = computeSelectedTotals();
            badgeQty.textContent = this._fmt(total);
            badgeUnit.textContent = "m²";
            footerQty.textContent = `${this._fmt(total)} m²`;
        };

        const updateBadge = () => {
            badgeCount.textContent = state.pending.size;
            updateQtyDisplay();
        };

        const updateStats = () => {
            stat.className = "hold-stone-filter-stat-count";
            stat.innerHTML = `${state.total} placas`;
            footerInfo.innerHTML = `Mostrando <strong>${state.quants.length}</strong> de <strong>${state.total}</strong>`;
        };

        const loadProducts = async () => {
            if (!productSelect) return;

            try {
                const records = await this.orm.searchRead(
                    "stock.quant",
                    [
                        ["location_id.usage", "=", "internal"],
                        ["quantity", ">", 0],
                        ["lot_id", "!=", false],
                    ],
                    ["product_id"],
                    { limit: 800 }
                );

                const seen = new Set();
                const products = [];

                for (const quant of records) {
                    if (quant.product_id && !seen.has(quant.product_id[0])) {
                        seen.add(quant.product_id[0]);
                        products.push({
                            id: quant.product_id[0],
                            name: quant.product_id[1],
                        });
                    }
                }

                products.sort((a, b) => a.name.localeCompare(b.name));

                for (const product of products) {
                    const option = document.createElement("option");
                    option.value = product.id;
                    option.textContent = product.name;
                    productSelect.appendChild(option);
                }
            } catch (error) {
                console.error("[HOLD STONE] Error cargando productos:", error);
            }
        };

        const selectAll = () => {
            for (const quant of state.quants) {
                const lotId = quant.lot_id ? quant.lot_id[0] : 0;
                if (!lotId) continue;
                state.pending.add(lotId);
                rememberQuant(quant);
            }

            updateBadge();
            renderTable();
        };

        const clearAll = () => {
            state.pending.clear();
            state.pendingQtyMap = {};
            updateBadge();
            renderTable();
        };

        const renderTable = () => {
            if (!state.quants.length && !state.loading) {
                body.innerHTML = `
                    <div class="hold-stone-empty-state">
                        <i class="fa fa-inbox fa-3x text-muted"></i>
                        <div class="hold-stone-empty-text mt-2">Sin resultados</div>
                    </div>
                `;
                updateStats();
                updateBadge();
                return;
            }

            let rows = "";

            for (const quant of state.quants) {
                const lotId = quant.lot_id ? quant.lot_id[0] : 0;
                const lotName = quant.lot_id ? quant.lot_id[1] : "—";
                const locationName = quant.location_id ? quant.location_id[1].split("/").pop() : "—";
                const selected = state.pending.has(lotId);
                const reserved = quant.reserved_quantity > 0;
                const tipo = (quant.x_tipo || "placa").toLowerCase();

                if (selected) {
                    rememberQuant(quant);
                }

                let badge = `<span class="hold-stone-tag hold-stone-tag-free">Libre</span>`;
                if (selected) {
                    badge = `<span class="hold-stone-tag hold-stone-tag-ok">Selec.</span>`;
                } else if (reserved) {
                    badge = `<span class="hold-stone-tag hold-stone-tag-warn">Reservado</span>`;
                }

                // M²: FORMATOS/PIEZAS seleccionados muestran un input para ajustar
                // la cantidad a apartar de ese lote (parcialidad), sin salir del
                // popup. PLACAS y filas no seleccionadas muestran el total del lote.
                const isPartial = tipo === "formato" || tipo === "pieza";
                let m2Cell = this._fmt(quant.quantity);
                if (selected && isPartial) {
                    const chosenQty = getQtyForLot(lotId);
                    const step = tipo === "pieza" ? "1" : "0.01";
                    const unit = tipo === "pieza" ? "pzas" : "m²";
                    m2Cell = `
                        <input type="number" class="hold-stone-popup-qty-input"
                               data-lot-id="${lotId}" data-max="${quant.quantity}"
                               step="${step}" min="0" max="${quant.quantity}"
                               value="${chosenQty}"
                               style="width: 76px; text-align: right;"/>
                        <span class="text-muted" style="font-size: 10px; margin-left: 2px;">/ ${this._fmt(quant.quantity)} ${unit}</span>
                    `;
                }

                rows += `
                    <tr class="${selected ? "row-sel" : ""}"
                        data-lot-id="${lotId}"
                        data-reserved="${reserved ? "1" : "0"}">
                        <td class="col-chk">
                            <div class="hold-stone-chkbox ${selected ? "checked" : ""}">
                                ${selected ? '<i class="fa fa-check"></i>' : ""}
                            </div>
                        </td>
                        <td class="cell-lot">${this._escapeHtml(lotName)}</td>
                        <td>${this._escapeHtml(quant.x_bloque || "—")}</td>
                        <td>${this._escapeHtml(quant.x_atado || "—")}</td>
                        <td class="col-num">${this._fmtDim(quant.x_alto)}</td>
                        <td class="col-num">${this._fmtDim(quant.x_ancho)}</td>
                        <td class="col-num">${this._fmtDim(quant.x_grosor)}</td>
                        <td class="col-num fw-semibold col-qty-input">${m2Cell}</td>
                        <td>
                            <span class="hold-stone-tag hold-stone-tag-tipo-${this._escapeHtml(tipo)}">
                                ${this._escapeHtml(this._tipoLabel(tipo))}
                            </span>
                        </td>
                        <td>${this._escapeHtml(quant.x_color || "—")}</td>
                        <td class="cell-loc">${this._escapeHtml(locationName)}</td>
                        <td>${badge}</td>
                    </tr>
                `;
            }

            const sentinel = `
                <div id="hold-popup-sentinel" class="hold-stone-scroll-sentinel">
                    ${
                        state.loadingMore
                            ? '<div class="hold-stone-loading-more"><i class="fa fa-circle-o-notch fa-spin me-2"></i>Cargando más...</div>'
                            : ""
                    }
                    ${
                        state.hasMore && !state.loadingMore
                            ? '<div class="hold-stone-scroll-hint"><i class="fa fa-chevron-down me-1"></i>Desplázate para cargar más</div>'
                            : ""
                    }
                </div>
            `;

            body.innerHTML = `
                <table class="hold-stone-popup-table">
                    <thead>
                        <tr>
                            <th class="col-chk">✓</th>
                            <th>Lote</th>
                            <th>Bloque</th>
                            <th>Atado</th>
                            <th class="col-num">Alto</th>
                            <th class="col-num">Largo</th>
                            <th class="col-num">Esp.</th>
                            <th class="col-num">M²</th>
                            <th>Tipo</th>
                            <th>Color</th>
                            <th>Ubicación</th>
                            <th>Estado</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                ${sentinel}
            `;

            updateStats();
            updateBadge();

            body.querySelectorAll("tr[data-lot-id]").forEach((tr) => {
                tr.addEventListener("click", () => {
                    const lotId = parseInt(tr.dataset.lotId, 10);
                    if (!lotId) return;

                    const quant = getQuantByLotId(lotId);

                    if (state.pending.has(lotId)) {
                        state.pending.delete(lotId);
                        delete state.pendingQtyMap[String(lotId)];
                    } else {
                        state.pending.add(lotId);
                        if (quant) rememberQuant(quant);
                    }

                    updateBadge();
                    renderTable();
                });
            });

            // Inputs de parcialidad (FORMATO/PIEZA): editar la cantidad no debe
            // alternar la selección de la fila (stopPropagation) y actualiza el
            // total en vivo sin re-render para no perder el foco del campo.
            body.querySelectorAll(".hold-stone-popup-qty-input").forEach((input) => {
                const stop = (event) => event.stopPropagation();
                input.addEventListener("click", stop);
                input.addEventListener("mousedown", stop);

                const apply = (normalize) => {
                    const lotId = parseInt(input.dataset.lotId, 10);
                    if (!lotId) return;
                    const maxQty = parseFloat(input.dataset.max) || 0;
                    let val = parseFloat(input.value);
                    if (Number.isNaN(val) || val < 0) val = 0;
                    if (maxQty && val > maxQty) val = maxQty;
                    state.pendingQtyMap[String(lotId)] = val;
                    if (normalize) input.value = val;
                    updateQtyDisplay();
                };

                input.addEventListener("input", (event) => {
                    event.stopPropagation();
                    apply(false);
                });
                input.addEventListener("change", (event) => {
                    event.stopPropagation();
                    apply(true);
                });
            });

            if (this._popupObserver) {
                this._popupObserver.disconnect();
                this._popupObserver = null;
            }

            const sentinelEl = body.querySelector("#hold-popup-sentinel");
            if (sentinelEl && state.hasMore) {
                this._popupObserver = new IntersectionObserver(
                    (entries) => {
                        if (entries[0].isIntersecting && state.hasMore && !state.loadingMore) {
                            loadPage(state.page + 1, false);
                        }
                    },
                    { root: body, rootMargin: "100px", threshold: 0.1 }
                );
                this._popupObserver.observe(sentinelEl);
            }
        };

        const loadPage = async (page, reset) => {
            if (reset) {
                state.loading = true;
                state.quants = [];

                body.innerHTML = `
                    <div class="hold-stone-empty-state">
                        <i class="fa fa-circle-o-notch fa-spin fa-2x text-muted"></i>
                        <div class="hold-stone-empty-text mt-2">Buscando...</div>
                    </div>
                `;

                stat.className = "hold-stone-filter-stat-loading";
                stat.innerHTML = `<i class="fa fa-circle-o-notch fa-spin me-1"></i>Buscando...`;
            } else {
                state.loadingMore = true;
            }

            try {
                const currentIds = Array.from(state.pending);

                const domain = [
                    ["location_id.usage", "=", "internal"],
                    ["quantity", ">", 0],
                    ["lot_id", "!=", false],
                ];

                if (state.productId) {
                    domain.push(["product_id", "=", state.productId]);
                }

                if (currentIds.length) {
                    domain.push("|");
                    domain.push("&");
                    domain.push(["x_tiene_hold", "=", false]);
                    domain.push(["reserved_quantity", "=", 0]);
                    domain.push(["lot_id", "in", currentIds]);
                } else {
                    domain.push(["x_tiene_hold", "=", false]);
                    domain.push(["reserved_quantity", "=", 0]);
                }

                if (state.filters.lot_name) {
                    domain.push(["lot_id.name", "ilike", state.filters.lot_name]);
                }

                if (state.filters.bloque) {
                    domain.push(["lot_id.x_bloque", "ilike", state.filters.bloque]);
                }

                if (state.filters.atado) {
                    domain.push(["lot_id.x_atado", "ilike", state.filters.atado]);
                }

                if (state.filters.tipo) {
                    domain.push(["lot_id.x_tipo", "=", state.filters.tipo]);
                }

                if (state.filters.alto_min) {
                    domain.push(["lot_id.x_alto", ">=", parseFloat(state.filters.alto_min)]);
                }

                if (state.filters.ancho_min) {
                    domain.push(["lot_id.x_ancho", ">=", parseFloat(state.filters.ancho_min)]);
                }

                const fields = [
                    "lot_id",
                    "product_id",
                    "location_id",
                    "quantity",
                    "reserved_quantity",
                    "x_grosor",
                    "x_alto",
                    "x_ancho",
                    "x_bloque",
                    "x_atado",
                    "x_tipo",
                    "x_color",
                ];

                const total = await this.orm.searchCount("stock.quant", domain);
                const offset = page * PAGE_SIZE;

                const quants = await this.orm.searchRead(
                    "stock.quant",
                    domain,
                    fields,
                    {
                        limit: PAGE_SIZE,
                        offset,
                        order: "lot_id",
                    }
                );

                if (reset || page === 0) {
                    state.quants = quants;
                } else {
                    state.quants = [...state.quants, ...quants];
                }

                state.total = total;
                state.page = page;
                state.hasMore = state.quants.length < total;

                for (const quant of quants) {
                    const lotId = quant.lot_id ? quant.lot_id[0] : 0;
                    if (lotId && state.pending.has(lotId)) {
                        rememberQuant(quant);
                    }
                }
            } catch (error) {
                body.innerHTML = `
                    <div class="hold-stone-empty-state">
                        <i class="fa fa-exclamation-triangle fa-2x text-danger"></i>
                        <div class="hold-stone-empty-text mt-2 text-danger">
                            ${this._escapeHtml(error.message)}
                        </div>
                    </div>
                `;
                return;
            } finally {
                state.loading = false;
                state.loadingMore = false;
            }

            renderTable();
        };

        const confirm = async () => {
            const newIds = Array.from(state.pending);

            // Se guarda la parcialidad por lote elegida en el popup:
            // - FORMATO/PIEZA: la cantidad ajustada (default = lote completo).
            // - PLACA: sin entrada (siempre se aparta el lote completo).
            // - Lotes preseleccionados que no se cargaron en el popup (filtros):
            //   se conserva su parcialidad previamente guardada.
            const prev = this._getCurrentBreakdownMap();
            const breakdown = {};
            for (const lotId of newIds) {
                const key = String(lotId);
                const tipo = state.tipoByLot[key];
                if (tipo === "formato" || tipo === "pieza") {
                    breakdown[key] = getQtyForLot(lotId);
                } else if (tipo === undefined && prev[key] !== undefined) {
                    breakdown[key] = prev[key];
                }
            }

            this.destroyPopup();
            await this._commitSelectionToServer(newIds, breakdown);
            await this._refreshDetail();
        };

        const close = () => this.destroyPopup();

        root.querySelector("#hold-popup-close").addEventListener("click", close);
        root.querySelector("#hold-popup-cancel").addEventListener("click", close);
        root.querySelector("#hold-popup-confirm-top").addEventListener("click", confirm);
        root.querySelector("#hold-popup-confirm-bottom").addEventListener("click", confirm);
        root.querySelector("#hold-popup-select-all").addEventListener("click", selectAll);
        root.querySelector("#hold-popup-clear-all").addEventListener("click", clearAll);

        overlay.addEventListener("click", (event) => {
            if (event.target === overlay) close();
        });

        const onKeyDown = (event) => {
            if (event.key === "Escape") close();
        };

        document.addEventListener("keydown", onKeyDown);
        this._popupKeyHandler = onKeyDown;

        const scheduleSearch = () => {
            if (searchTimer) clearTimeout(searchTimer);
            searchTimer = setTimeout(() => loadPage(0, true), 350);
        };

        const bindFilter = (id, key) => {
            const input = root.querySelector(`#${id}`);
            if (!input) return;

            const handler = (event) => {
                state.filters[key] = event.target.value;
                scheduleSearch();
            };

            input.addEventListener("input", handler);
            input.addEventListener("change", handler);
        };

        bindFilter("hold-filter-lot", "lot_name");
        bindFilter("hold-filter-block", "bloque");
        bindFilter("hold-filter-bundle", "atado");
        bindFilter("hold-filter-height", "alto_min");
        bindFilter("hold-filter-width", "ancho_min");
        bindFilter("hold-filter-type", "tipo");

        if (productSelect) {
            productSelect.addEventListener("change", (event) => {
                state.productId = event.target.value ? parseInt(event.target.value, 10) : 0;
                loadPage(0, true);
            });
        }

        loadProducts().then(() => loadPage(0, true));
    }

    destroyPopup() {
        if (this._popupObserver) {
            this._popupObserver.disconnect();
            this._popupObserver = null;
        }

        if (this._popupKeyHandler) {
            document.removeEventListener("keydown", this._popupKeyHandler);
            this._popupKeyHandler = null;
        }

        if (this._popupRoot) {
            this._popupRoot.remove();
            this._popupRoot = null;
        }
    }
}

HoldStoneButton.template = "stock_lot_dimensions.HoldStoneButton";

registry.category("fields").add("hold_stone_button", {
    component: HoldStoneButton,
    displayName: "Botón Selección Piedra (Hold)",
});