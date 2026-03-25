/** @odoo-module */
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState, onWillStart, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * HoldStoneButton — Widget para seleccionar placas en stock.lot.hold.order.line
 * 
 * Replica el UX de StoneExpandButton (sale_stone_selection) pero adaptado al modelo
 * de órdenes de reserva. Al seleccionar un lote, se escribe lot_id, product_id,
 * quant_id y cantidad_m2 directamente en la línea.
 */
export class HoldStoneButton extends Component {
    static template = "stock_lot_dimensions.HoldStoneButton";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this._detailsRow = null;
        this._popupRoot = null;
        this._popupKeyHandler = null;
        this._popupObserver = null;

        this.state = useState({
            isExpanded: false,
            hasLot: false,
        });

        onWillStart(() => this._updateState());
        onWillUpdateProps(() => this._updateState());
        onWillUnmount(() => {
            this.removeDetailsRow();
            this.destroyPopup();
        });
    }

    _updateState() {
        const data = this.props.record.data;
        this.state.hasLot = !!(data.lot_id && this._extractId(data.lot_id));
    }

    _extractId(field) {
        if (!field) return 0;
        if (typeof field === "number") return field;
        if (Array.isArray(field)) return field[0] || 0;
        if (field.id) return field.id;
        return 0;
    }

    _extractName(field) {
        if (!field) return "";
        if (Array.isArray(field)) return field[1] || "";
        if (field.display_name) return field.display_name;
        if (field.name) return field.name;
        return "";
    }

    getProductId() {
        return this._extractId(this.props.record.data.product_id);
    }

    getProductName() {
        return this._extractName(this.props.record.data.product_id);
    }

    getLotId() {
        return this._extractId(this.props.record.data.lot_id);
    }

    // ─── Toggle principal ─────────────────────────────────────────────────────

    async handleToggle(ev) {
        ev.stopPropagation();

        if (this.state.isExpanded) {
            this.removeDetailsRow();
            this.state.isExpanded = false;
            return;
        }

        // Cerrar otros expandidos
        document.querySelectorAll(".hold-stone-selected-row").forEach((e) => e.remove());

        const tr = ev.currentTarget.closest("tr");
        if (!tr) return;

        this.state.isExpanded = true;
        await this.injectSelectedInfo(tr);
    }

    // ─── Info inline del lote seleccionado ─────────────────────────────────────

    async injectSelectedInfo(currentRow) {
        const newTr = document.createElement("tr");
        newTr.className = "hold-stone-selected-row stone-selected-row";

        const colCount = currentRow.querySelectorAll("td").length || 10;
        const td = document.createElement("td");
        td.colSpan = colCount;
        td.className = "stone-selected-cell";

        const container = document.createElement("div");
        container.className = "stone-selected-container";

        const header = document.createElement("div");
        header.className = "stone-selected-header";
        
        const lotId = this.getLotId();
        const lotLabel = lotId ? "1 placa seleccionada" : "Sin placa seleccionada";
        
        header.innerHTML = `
            <span class="stone-selected-title">
                <i class="fa fa-check-circle me-2"></i>
                ${lotLabel}
            </span>
            <div style="display:flex;gap:6px;">
                <button class="stone-add-btn hold-change-btn">
                    <i class="fa fa-th-large me-1"></i> ${lotId ? "Cambiar placa" : "Seleccionar placa"}
                </button>
                ${lotId ? `<button class="stone-add-btn hold-remove-btn" style="background:#e53e3e;">
                    <i class="fa fa-times me-1"></i> Quitar
                </button>` : ""}
            </div>
        `;

        const body = document.createElement("div");
        body.className = "stone-selected-body";

        container.appendChild(header);
        container.appendChild(body);
        td.appendChild(container);
        newTr.appendChild(td);
        currentRow.after(newTr);
        this._detailsRow = newTr;

        if (lotId) {
            await this.renderLotInfo(body, lotId);
        } else {
            body.innerHTML = `
                <div class="stone-no-selection">
                    <i class="fa fa-info-circle me-2 text-muted"></i>
                    <span class="text-muted">Usa <strong>Seleccionar placa</strong> para elegir un lote del inventario.</span>
                </div>`;
        }

        header.querySelector(".hold-change-btn").addEventListener("click", (e) => {
            e.stopPropagation();
            this.openPopup();
        });

        const removeBtn = header.querySelector(".hold-remove-btn");
        if (removeBtn) {
            removeBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                await this.clearLot();
            });
        }
    }

    async renderLotInfo(container, lotId) {
        container.innerHTML = `<div class="stone-table-loading"><i class="fa fa-circle-o-notch fa-spin me-2"></i> Cargando datos...</div>`;

        try {
            const [lotsData, quants] = await Promise.all([
                this.orm.searchRead(
                    "stock.lot",
                    [["id", "=", lotId]],
                    ["name", "x_bloque", "x_atado", "x_alto", "x_ancho", "x_grosor", "x_tipo", "x_color", "x_pedimento", "x_contenedor"],
                    { limit: 1 }
                ),
                this.orm.searchRead(
                    "stock.quant",
                    [["lot_id", "=", lotId], ["location_id.usage", "=", "internal"], ["quantity", ">", 0]],
                    ["lot_id", "quantity"],
                    { limit: 1 }
                ),
            ]);

            if (!lotsData.length) {
                container.innerHTML = `<div class="p-2 text-muted">Lote no encontrado</div>`;
                return;
            }

            const lot = lotsData[0];
            const qty = quants.length ? quants[0].quantity : 0;

            container.innerHTML = `
                <table class="stone-sel-table">
                    <thead>
                        <tr>
                            <th>Lote</th>
                            <th>Bloque</th>
                            <th>Atado</th>
                            <th class="col-num">Alto</th>
                            <th class="col-num">Ancho</th>
                            <th class="col-num">Espesor</th>
                            <th class="col-num">M²</th>
                            <th>Tipo</th>
                            <th>Color</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td class="cell-lot">${lot.name}</td>
                            <td>${lot.x_bloque || "-"}</td>
                            <td>${lot.x_atado || "-"}</td>
                            <td class="col-num">${lot.x_alto ? lot.x_alto.toFixed(0) : "-"}</td>
                            <td class="col-num">${lot.x_ancho ? lot.x_ancho.toFixed(0) : "-"}</td>
                            <td class="col-num">${lot.x_grosor || "-"}</td>
                            <td class="col-num fw-semibold">${qty.toFixed(2)}</td>
                            <td>${lot.x_tipo || "-"}</td>
                            <td>${lot.x_color || "-"}</td>
                        </tr>
                    </tbody>
                </table>`;
        } catch (err) {
            console.error("[HOLD STONE] Error:", err);
            container.innerHTML = `<div class="text-danger p-2">Error: ${err.message}</div>`;
        }
    }

    async clearLot() {
        await this.props.record.update({
            lot_id: false,
            quant_id: false,
            cantidad_m2: 0,
        });
        this._updateState();
        this.removeDetailsRow();
        this.state.isExpanded = false;
    }

    removeDetailsRow() {
        if (this._detailsRow) {
            this._detailsRow.remove();
            this._detailsRow = null;
        }
    }

    // ─── POPUP ────────────────────────────────────────────────────────────────

    openPopup() {
        this.destroyPopup();

        // Intentar obtener product_id del contexto de la orden (parent)
        // En hold.order.line no siempre hay product_id pre-seleccionado
        let productId = this.getProductId();

        this._popupRoot = document.createElement("div");
        this._popupRoot.className = "stone-popup-root";
        document.body.appendChild(this._popupRoot);

        this._renderPopupDOM(productId);
    }

    _renderPopupDOM(initialProductId) {
        const root = this._popupRoot;
        const PAGE_SIZE = 35;

        const popupState = {
            quants: [],
            totalCount: 0,
            hasMore: false,
            isLoading: false,
            isLoadingMore: false,
            page: 0,
            selectedLotId: this.getLotId() || null,
            filters: { lot_name: "", bloque: "", atado: "", alto_min: "", ancho_min: "" },
            productId: initialProductId,
            products: [],
        };

        let searchTimeout = null;

        root.innerHTML = `
            <div class="stone-popup-overlay" id="hold-overlay">
                <div class="stone-popup-container">
                    <div class="stone-popup-header">
                        <div class="stone-popup-title">
                            <i class="fa fa-th me-2"></i>
                            Seleccionar Placa para Reserva
                        </div>
                        <div class="stone-popup-header-actions">
                            <span class="stone-badge-selected">
                                <i class="fa fa-check-circle me-1"></i>
                                <span id="hp-badge">${popupState.selectedLotId ? "1" : "0"}</span> seleccionada
                            </span>
                            <button class="stone-btn stone-btn-accent" id="hp-confirm-top">
                                <i class="fa fa-check me-1"></i> Confirmar
                            </button>
                            <button class="stone-btn stone-btn-ghost" id="hp-close">
                                <i class="fa fa-times"></i>
                            </button>
                        </div>
                    </div>

                    <div class="stone-popup-filters">
                        <div class="stone-filter-group">
                            <label>Producto</label>
                            <select class="stone-filter-input" id="hf-product" style="width:220px;">
                                <option value="">Todos los productos</option>
                            </select>
                        </div>
                        <div class="stone-filter-group">
                            <label>Lote</label>
                            <input type="text" class="stone-filter-input" id="hf-lot" placeholder="Buscar lote..."/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Bloque</label>
                            <input type="text" class="stone-filter-input" id="hf-bloque" placeholder="Bloque..."/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Atado</label>
                            <input type="text" class="stone-filter-input" id="hf-atado" placeholder="Atado..."/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Alto mín.</label>
                            <input type="number" class="stone-filter-input stone-filter-sm" id="hf-alto" placeholder="0"/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Ancho mín.</label>
                            <input type="number" class="stone-filter-input stone-filter-sm" id="hf-ancho" placeholder="0"/>
                        </div>
                        <div class="stone-filter-spacer"></div>
                        <div class="stone-filter-stats">
                            <span id="hp-stat" class="stone-filter-stat-loading">
                                <i class="fa fa-circle-o-notch fa-spin me-1"></i> Buscando...
                            </span>
                        </div>
                    </div>

                    <div class="stone-popup-body" id="hp-body">
                        <div class="stone-empty-state">
                            <i class="fa fa-circle-o-notch fa-spin fa-2x text-muted"></i>
                            <div class="stone-empty-text mt-2">Cargando inventario...</div>
                        </div>
                    </div>

                    <div class="stone-popup-footer">
                        <span class="stone-footer-info" id="hp-footer-info">—</span>
                        <div class="stone-footer-actions">
                            <button class="stone-btn stone-btn-outline" id="hp-cancel">Cancelar</button>
                            <button class="stone-btn stone-btn-primary-dark" id="hp-confirm-bottom">
                                <i class="fa fa-check me-1"></i> Confirmar selección
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        const overlay = root.querySelector("#hold-overlay");
        const body = root.querySelector("#hp-body");
        const stat = root.querySelector("#hp-stat");
        const footerInfo = root.querySelector("#hp-footer-info");
        const badge = root.querySelector("#hp-badge");
        const productSelect = root.querySelector("#hf-product");

        const updateBadge = () => { badge.textContent = popupState.selectedLotId ? "1" : "0"; };
        const updateStats = () => {
            stat.className = "stone-filter-stat-count";
            stat.innerHTML = `${popupState.totalCount} placas disponibles`;
            footerInfo.innerHTML = `Mostrando <strong>${popupState.quants.length}</strong> de <strong>${popupState.totalCount}</strong>`;
        };

        // Cargar lista de productos con stock
        const loadProducts = async () => {
            try {
                const products = await this.orm.searchRead(
                    "stock.quant",
                    [["location_id.usage", "=", "internal"], ["quantity", ">", 0], ["lot_id", "!=", false]],
                    ["product_id"],
                    { limit: 500 }
                );
                const seen = new Set();
                popupState.products = [];
                for (const q of products) {
                    if (q.product_id && !seen.has(q.product_id[0])) {
                        seen.add(q.product_id[0]);
                        popupState.products.push({ id: q.product_id[0], name: q.product_id[1] });
                    }
                }
                popupState.products.sort((a, b) => a.name.localeCompare(b.name));
                
                productSelect.innerHTML = `<option value="">Todos los productos</option>`;
                for (const p of popupState.products) {
                    const opt = document.createElement("option");
                    opt.value = p.id;
                    opt.textContent = p.name;
                    if (p.id === popupState.productId) opt.selected = true;
                    productSelect.appendChild(opt);
                }
            } catch (e) {
                console.error("[HOLD STONE] Error cargando productos:", e);
            }
        };

        const renderTable = () => {
            if (popupState.quants.length === 0 && !popupState.isLoading) {
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-inbox fa-3x text-muted"></i>
                        <div class="stone-empty-text mt-2">No hay placas con estos filtros</div>
                    </div>`;
                updateStats();
                return;
            }

            let rows = "";
            for (const q of popupState.quants) {
                const lotId = q.lot_id ? q.lot_id[0] : 0;
                const lotName = q.lot_id ? q.lot_id[1] : "-";
                const productName = q.product_name || "";
                const loc = q.location_id ? q.location_id[1].split("/").pop() : "-";
                const sel = popupState.selectedLotId === lotId;
                const reserved = q.reserved_quantity > 0;

                let statusBadge = `<span class="stone-tag stone-tag-free">Libre</span>`;
                if (sel) statusBadge = `<span class="stone-tag stone-tag-ok">Selec.</span>`;
                else if (reserved) statusBadge = `<span class="stone-tag stone-tag-warn">Reservado</span>`;

                rows += `
                    <tr class="${sel ? "row-sel" : ""}" data-lot-id="${lotId}" data-quant-id="${q.id}" data-product-id="${q.product_id}" data-qty="${q.quantity || 0}">
                        <td class="col-chk">
                            <div class="stone-chkbox ${sel ? "checked" : ""}">
                                ${sel ? '<i class="fa fa-check"></i>' : ""}
                            </div>
                        </td>
                        <td class="cell-lot">${lotName}</td>
                        <td class="small text-muted" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${productName}</td>
                        <td>${q.x_bloque || "-"}</td>
                        <td>${q.x_atado || "-"}</td>
                        <td class="col-num">${q.x_alto ? q.x_alto.toFixed(0) : "-"}</td>
                        <td class="col-num">${q.x_ancho ? q.x_ancho.toFixed(0) : "-"}</td>
                        <td class="col-num">${q.x_grosor || "-"}</td>
                        <td class="col-num fw-semibold">${q.quantity ? q.quantity.toFixed(2) : "-"}</td>
                        <td>${q.x_tipo || "-"}</td>
                        <td>${q.x_color || "-"}</td>
                        <td class="cell-loc">${loc}</td>
                        <td>${statusBadge}</td>
                    </tr>`;
            }

            const sentinel = `
                <div id="hp-sentinel" class="stone-scroll-sentinel">
                    ${popupState.isLoadingMore ? '<div class="stone-loading-more"><i class="fa fa-circle-o-notch fa-spin me-2"></i> Cargando más...</div>' : ""}
                    ${popupState.hasMore && !popupState.isLoadingMore ? '<div class="stone-scroll-hint"><i class="fa fa-chevron-down me-1"></i> Desplázate para cargar más</div>' : ""}
                </div>`;

            body.innerHTML = `
                <table class="stone-popup-table">
                    <thead>
                        <tr>
                            <th class="col-chk">✓</th>
                            <th>Lote</th>
                            <th>Producto</th>
                            <th>Bloque</th>
                            <th>Atado</th>
                            <th class="col-num">Alto</th>
                            <th class="col-num">Ancho</th>
                            <th class="col-num">Gros.</th>
                            <th class="col-num">M²</th>
                            <th>Tipo</th>
                            <th>Color</th>
                            <th>Ubicación</th>
                            <th>Estado</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                ${sentinel}`;

            updateStats();

            // Click en filas — selección ÚNICA (radio, no checkbox)
            body.querySelectorAll("tr[data-lot-id]").forEach((tr) => {
                tr.style.cursor = "pointer";
                tr.addEventListener("click", () => {
                    const lotId = parseInt(tr.dataset.lotId);
                    if (!lotId) return;

                    // Toggle: si ya está seleccionado, deseleccionar
                    if (popupState.selectedLotId === lotId) {
                        popupState.selectedLotId = null;
                    } else {
                        popupState.selectedLotId = lotId;
                    }
                    popupState._selectedQuantId = parseInt(tr.dataset.quantId) || 0;
                    popupState._selectedProductId = parseInt(tr.dataset.productId) || 0;
                    popupState._selectedQty = parseFloat(tr.dataset.qty) || 0;

                    // Actualizar visual de TODAS las filas
                    body.querySelectorAll("tr[data-lot-id]").forEach((row) => {
                        const rid = parseInt(row.dataset.lotId);
                        const isSel = popupState.selectedLotId === rid;
                        row.className = isSel ? "row-sel" : "";
                        const chk = row.querySelector(".stone-chkbox");
                        if (chk) {
                            chk.className = "stone-chkbox" + (isSel ? " checked" : "");
                            chk.innerHTML = isSel ? '<i class="fa fa-check"></i>' : "";
                        }
                        const tag = row.querySelector(".stone-tag");
                        if (tag) {
                            if (isSel) {
                                tag.className = "stone-tag stone-tag-ok";
                                tag.textContent = "Selec.";
                            } else {
                                const reserved = row.dataset.reserved === "1";
                                tag.className = reserved ? "stone-tag stone-tag-warn" : "stone-tag stone-tag-free";
                                tag.textContent = reserved ? "Reservado" : "Libre";
                            }
                        }
                    });
                    updateBadge();
                });
            });

            // Infinite scroll
            if (this._popupObserver) {
                this._popupObserver.disconnect();
                this._popupObserver = null;
            }
            const sentinelEl = body.querySelector("#hp-sentinel");
            if (sentinelEl && popupState.hasMore) {
                this._popupObserver = new IntersectionObserver(
                    (entries) => {
                        if (entries[0].isIntersecting && popupState.hasMore && !popupState.isLoadingMore) {
                            loadPage(popupState.page + 1, false);
                        }
                    },
                    { root: body, rootMargin: "100px", threshold: 0.1 }
                );
                this._popupObserver.observe(sentinelEl);
            }
        };

        const loadPage = async (page, reset) => {
            if (reset) {
                popupState.isLoading = true;
                popupState.quants = [];
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-circle-o-notch fa-spin fa-2x text-muted"></i>
                        <div class="stone-empty-text mt-2">Buscando...</div>
                    </div>`;
                stat.className = "stone-filter-stat-loading";
                stat.innerHTML = `<i class="fa fa-circle-o-notch fa-spin me-1"></i> Buscando...`;
            } else {
                popupState.isLoadingMore = true;
            }

            try {
                // Construir dominio directo en stock.quant
                const domain = [
                    ["location_id.usage", "=", "internal"],
                    ["quantity", ">", 0],
                    ["lot_id", "!=", false],
                ];

                if (popupState.productId) {
                    domain.push(["product_id", "=", popupState.productId]);
                }
                if (popupState.filters.lot_name) {
                    domain.push(["lot_id.name", "ilike", popupState.filters.lot_name]);
                }
                if (popupState.filters.bloque) {
                    domain.push(["lot_id.x_bloque", "ilike", popupState.filters.bloque]);
                }
                if (popupState.filters.atado) {
                    domain.push(["lot_id.x_atado", "ilike", popupState.filters.atado]);
                }
                if (popupState.filters.alto_min) {
                    domain.push(["lot_id.x_alto", ">=", parseFloat(popupState.filters.alto_min)]);
                }
                if (popupState.filters.ancho_min) {
                    domain.push(["lot_id.x_ancho", ">=", parseFloat(popupState.filters.ancho_min)]);
                }

                // Excluir quants con hold activo
                domain.push(["x_tiene_hold", "=", false]);
                // Excluir reservados por sistema
                domain.push(["reserved_quantity", "=", 0]);

                const fields = [
                    "lot_id", "product_id", "location_id", "quantity", "reserved_quantity",
                    "x_grosor", "x_alto", "x_ancho", "x_bloque", "x_atado",
                    "x_tipo", "x_color", "x_pedimento", "x_contenedor",
                ];

                const total = await this.orm.searchCount("stock.quant", domain);
                const offset = page * PAGE_SIZE;
                const quants = await this.orm.searchRead("stock.quant", domain, fields, {
                    limit: PAGE_SIZE,
                    offset,
                    order: "lot_id",
                });

                const items = quants.map((q) => ({
                    ...q,
                    product_id: q.product_id ? q.product_id[0] : 0,
                    product_name: q.product_id ? q.product_id[1] : "",
                }));

                if (reset || page === 0) {
                    popupState.quants = items;
                } else {
                    popupState.quants = [...popupState.quants, ...items];
                }
                popupState.totalCount = total;
                popupState.page = page;
                popupState.hasMore = popupState.quants.length < total;
            } catch (err) {
                console.error("[HOLD STONE POPUP] Error:", err);
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-exclamation-triangle fa-2x text-danger"></i>
                        <div class="stone-empty-text mt-2 text-danger">Error: ${err.message}</div>
                    </div>`;
                return;
            } finally {
                popupState.isLoading = false;
                popupState.isLoadingMore = false;
            }

            renderTable();
        };

        // ─── Confirm / Close ─────────────────────────────────────────────────
        const doConfirm = async () => {
            if (popupState.selectedLotId) {
                // Buscar el quant para obtener datos completos
                const quantData = popupState.quants.find(
                    (q) => q.lot_id && q.lot_id[0] === popupState.selectedLotId
                );

                const updateVals = {
                    lot_id: popupState.selectedLotId,
                };

                if (quantData) {
                    updateVals.product_id = quantData.product_id || popupState._selectedProductId;
                    updateVals.quant_id = quantData.id || popupState._selectedQuantId;
                    updateVals.cantidad_m2 = quantData.quantity || popupState._selectedQty;
                } else {
                    // Fallback: datos del tr
                    if (popupState._selectedProductId) updateVals.product_id = popupState._selectedProductId;
                    if (popupState._selectedQuantId) updateVals.quant_id = popupState._selectedQuantId;
                    if (popupState._selectedQty) updateVals.cantidad_m2 = popupState._selectedQty;
                }

                await this.props.record.update(updateVals);
            }
            this.destroyPopup();
            this._updateState();
            
            // Refrescar la info inline si está abierta
            if (this._detailsRow) {
                this.removeDetailsRow();
                const tr = document.querySelector(`tr[data-id="${this.props.record.id}"]`) 
                    || document.querySelector(`.o_data_row`);
                if (tr) {
                    // Re-inject
                }
            }
            this.state.isExpanded = false;
        };

        const doClose = () => this.destroyPopup();

        // ─── Event listeners ─────────────────────────────────────────────────
        root.querySelector("#hp-close").addEventListener("click", doClose);
        root.querySelector("#hp-cancel").addEventListener("click", doClose);
        root.querySelector("#hp-confirm-top").addEventListener("click", doConfirm);
        root.querySelector("#hp-confirm-bottom").addEventListener("click", doConfirm);
        overlay.addEventListener("click", (e) => { if (e.target === overlay) doClose(); });

        const onKeyDown = (e) => { if (e.key === "Escape") doClose(); };
        document.addEventListener("keydown", onKeyDown);
        this._popupKeyHandler = onKeyDown;

        // Filtros
        const scheduleSearch = () => {
            if (searchTimeout) clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => loadPage(0, true), 350);
        };

        const bindFilter = (id, key) => {
            const input = root.querySelector(`#${id}`);
            if (!input) return;
            input.addEventListener("input", (e) => {
                popupState.filters[key] = e.target.value;
                scheduleSearch();
            });
        };
        bindFilter("hf-lot", "lot_name");
        bindFilter("hf-bloque", "bloque");
        bindFilter("hf-atado", "atado");
        bindFilter("hf-alto", "alto_min");
        bindFilter("hf-ancho", "ancho_min");

        productSelect.addEventListener("change", (e) => {
            popupState.productId = e.target.value ? parseInt(e.target.value) : 0;
            loadPage(0, true);
        });

        // Carga inicial
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

registry.category("fields").add("hold_stone_button", {
    component: HoldStoneButton,
    displayName: "Botón Selección Piedra (Hold)",
});