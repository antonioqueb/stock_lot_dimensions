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
        this._detailsRow = null;
        this._popupRoot = null;
        this._popupKeyHandler = null;
        this._popupObserver = null;

        this.state = useState({ isExpanded: false, selectedCount: 0 });

        onWillStart(() => this._updateCount());
        onWillUpdateProps((np) => this._updateCount(np));
        onWillUnmount(() => { this.removeDetailsRow(); this.destroyPopup(); });
    }

    _updateCount(props = this.props) {
        this.state.selectedCount = this._extractIds(props?.record?.data?.lot_ids).length;
    }

    _extractIds(raw) {
        if (!raw) return [];
        if (Array.isArray(raw)) return raw.filter(x => typeof x === "number");
        if (raw.currentIds) return raw.currentIds;
        if (raw.resIds) return raw.resIds;
        if (raw.records) return raw.records.map(r => r.resId || r.data?.id).filter(Boolean);
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

    getProductId() { return this._id(this.props.record.data.product_id); }
    getProductName() { return this._name(this.props.record.data.product_id); }
    getCurrentLotIds() { return this._extractIds(this.props.record.data.lot_ids); }

    // ─── Calcular m² total de los lotes seleccionados ─────────────────────
    async _computeM2ForLots(lotIds) {
        if (!lotIds || !lotIds.length) return 0.0;
        try {
            const quants = await this.orm.searchRead("stock.quant",
                [["lot_id", "in", lotIds], ["location_id.usage", "=", "internal"], ["quantity", ">", 0]],
                ["lot_id", "quantity"]);
            let total = 0.0;
            const seen = new Set();
            for (const q of quants) {
                const lid = q.lot_id[0];
                if (!seen.has(lid)) {
                    seen.add(lid);
                    total += q.quantity || 0;
                }
            }
            return total;
        } catch (e) {
            console.warn("Error computing m2:", e);
            return 0.0;
        }
    }

    // ─── Actualizar lot_ids Y cantidad_m2 juntos ──────────────────────────
    async _updateLotsAndM2(newLotIds) {
        const m2 = await this._computeM2ForLots(newLotIds);
        await this.props.record.update({
            lot_ids: [[6, 0, newLotIds]],
            cantidad_m2: m2,
        });
        this._updateCount();
    }

    // ─── Toggle ───────────────────────────────────────────────────────────────

    async handleToggle(ev) {
        ev.stopPropagation();
        if (this.state.isExpanded) {
            this.removeDetailsRow();
            this.state.isExpanded = false;
            return;
        }
        document.querySelectorAll(".hold-stone-selected-row").forEach(e => e.remove());
        const tr = ev.currentTarget.closest("tr");
        if (!tr) return;
        this.state.isExpanded = true;
        await this._injectDetail(tr);
    }

    // ─── Detalle inline ───────────────────────────────────────────────────────

    async _injectDetail(row) {
        const newTr = document.createElement("tr");
        newTr.className = "hold-stone-selected-row stone-selected-row";
        const td = document.createElement("td");
        td.colSpan = row.querySelectorAll("td").length || 10;
        td.className = "stone-selected-cell";

        const container = document.createElement("div");
        container.className = "stone-selected-container";

        const header = document.createElement("div");
        header.className = "stone-selected-header";
        const count = this.getCurrentLotIds().length;
        header.innerHTML = `
            <span class="stone-selected-title">
                <i class="fa fa-check-circle me-2"></i>Placas seleccionadas
                <span class="stone-sel-badge" id="hold-sel-badge">${count}</span>
            </span>
            <button class="stone-add-btn hold-add-btn-trigger">
                <i class="fa fa-plus me-1"></i> Agregar placa
            </button>`;

        const body = document.createElement("div");
        body.className = "stone-selected-body";

        container.appendChild(header);
        container.appendChild(body);
        td.appendChild(container);
        newTr.appendChild(td);
        row.after(newTr);
        this._detailsRow = newTr;

        await this._renderDetail(body, this.getCurrentLotIds());
        header.querySelector(".hold-add-btn-trigger").addEventListener("click", e => {
            e.stopPropagation();
            this.openPopup();
        });
    }

    async _renderDetail(container, lotIds) {
        if (!lotIds.length) {
            container.innerHTML = `<div class="stone-no-selection"><i class="fa fa-info-circle me-2 text-muted"></i>
                <span class="text-muted">Sin placas seleccionadas. Usa <strong>Agregar placa</strong> para comenzar.</span></div>`;
            return;
        }
        container.innerHTML = `<div class="stone-table-loading"><i class="fa fa-circle-o-notch fa-spin me-2"></i> Cargando...</div>`;

        try {
            const [lots, quants] = await Promise.all([
                this.orm.searchRead("stock.lot", [["id", "in", lotIds]],
                    ["name", "x_bloque", "x_atado", "x_alto", "x_ancho", "x_grosor", "x_tipo", "x_color"],
                    { limit: lotIds.length }),
                this.orm.searchRead("stock.quant",
                    [["lot_id", "in", lotIds], ["location_id.usage", "=", "internal"], ["quantity", ">", 0]],
                    ["lot_id", "quantity"]),
            ]);

            const qm = {};
            for (const q of quants) qm[q.lot_id[0]] = (qm[q.lot_id[0]] || 0) + q.quantity;
            const lm = {};
            for (const l of lots) lm[l.id] = l;

            let total = 0;
            let rows = "";
            for (const lid of lotIds) {
                const lot = lm[lid];
                if (!lot) continue;
                const qty = qm[lid] || 0;
                total += qty;
                rows += `<tr>
                    <td class="cell-lot">${lot.name}</td>
                    <td>${lot.x_bloque || "-"}</td><td>${lot.x_atado || "-"}</td>
                    <td class="col-num">${lot.x_alto ? lot.x_alto.toFixed(4) : "-"}</td>
                    <td class="col-num">${lot.x_ancho ? lot.x_ancho.toFixed(4) : "-"}</td>
                    <td class="col-num">${lot.x_grosor || "-"}</td>
                    <td class="col-num fw-semibold">${qty.toFixed(2)}</td>
                    <td>${lot.x_tipo || "-"}</td><td>${lot.x_color || "-"}</td>
                    <td class="col-act"><button class="stone-remove-btn" data-lot-id="${lid}" title="Quitar"><i class="fa fa-times"></i></button></td>
                </tr>`;
            }

            container.innerHTML = `<table class="stone-sel-table">
                <thead><tr><th>Lote</th><th>Bloque</th><th>Atado</th>
                    <th class="col-num">Alto</th><th class="col-num">Ancho</th><th class="col-num">Espesor</th>
                    <th class="col-num">M²</th><th>Tipo</th><th>Color</th><th class="col-act"></th></tr></thead>
                <tbody>${rows}</tbody>
                <tfoot><tr class="stone-total-row">
                    <td colspan="6" class="text-end fw-bold text-muted">Total:</td>
                    <td class="col-num fw-bold">${total.toFixed(2)}</td><td colspan="3"></td>
                </tr></tfoot></table>`;

            container.querySelectorAll(".stone-remove-btn").forEach(btn => {
                btn.addEventListener("click", e => { e.stopPropagation(); this._removeLot(parseInt(btn.dataset.lotId)); });
            });
        } catch (err) {
            container.innerHTML = `<div class="text-danger p-2">Error: ${err.message}</div>`;
        }
    }

    async _removeLot(lotId) {
        const newIds = this.getCurrentLotIds().filter(id => id !== lotId);
        await this._updateLotsAndM2(newIds);
        await this._refreshDetail();
    }

    async _refreshDetail() {
        if (!this._detailsRow) return;
        const body = this._detailsRow.querySelector(".stone-selected-body");
        if (!body) return;
        const ids = this.getCurrentLotIds();
        const badge = this._detailsRow.querySelector(".stone-sel-badge");
        if (badge) badge.textContent = ids.length;
        await this._renderDetail(body, ids);
    }

    removeDetailsRow() {
        if (this._detailsRow) { this._detailsRow.remove(); this._detailsRow = null; }
    }

    // ─── Popup ────────────────────────────────────────────────────────────────

    openPopup() {
        this.destroyPopup();
        this._popupRoot = document.createElement("div");
        this._popupRoot.className = "stone-popup-root";
        document.body.appendChild(this._popupRoot);
        this._buildPopup(this.getProductId());
    }

    _buildPopup(fixedProductId) {
        const root = this._popupRoot;
        const PS = 35;
        const S = {
            quants: [], total: 0, hasMore: false, loading: false, loadingMore: false,
            page: 0, pending: new Set(this.getCurrentLotIds()),
            filters: { lot_name: "", bloque: "", atado: "", alto_min: "", ancho_min: "" },
            productId: fixedProductId,
        };
        let timer = null;
        const showProd = !fixedProductId;

        root.innerHTML = `
        <div class="stone-popup-overlay" id="hp-ov">
            <div class="stone-popup-container">
                <div class="stone-popup-header">
                    <div class="stone-popup-title"><i class="fa fa-th me-2"></i>Seleccionar Placas
                        <span class="stone-popup-subtitle">${this.getProductName() ? "— " + this.getProductName() : ""}</span></div>
                    <div class="stone-popup-header-actions">
                        <span class="stone-badge-selected"><i class="fa fa-check-circle me-1"></i><span id="hp-bc">${S.pending.size}</span> selec.</span>
                        <button class="stone-btn stone-btn-accent" id="hp-ok1"><i class="fa fa-check me-1"></i>Confirmar</button>
                        <button class="stone-btn stone-btn-ghost" id="hp-x"><i class="fa fa-times"></i></button>
                    </div>
                </div>
                <div class="stone-popup-filters">
                    ${showProd ? '<div class="stone-filter-group"><label>Producto</label><select class="stone-filter-input" id="hf-prod" style="width:220px"><option value="">Todos</option></select></div>' : ""}
                    <div class="stone-filter-group"><label>Lote</label><input type="text" class="stone-filter-input" id="hf-lot" placeholder="Buscar..."/></div>
                    <div class="stone-filter-group"><label>Bloque</label><input type="text" class="stone-filter-input" id="hf-blq" placeholder="Bloque..."/></div>
                    <div class="stone-filter-group"><label>Atado</label><input type="text" class="stone-filter-input" id="hf-ata" placeholder="Atado..."/></div>
                    <div class="stone-filter-group"><label>Alto mín.</label><input type="number" class="stone-filter-input stone-filter-sm" id="hf-alt" placeholder="0"/></div>
                    <div class="stone-filter-group"><label>Ancho mín.</label><input type="number" class="stone-filter-input stone-filter-sm" id="hf-anc" placeholder="0"/></div>
                    <div class="stone-filter-actions">
                        <button class="stone-btn stone-btn-select-all" id="hp-sa"><i class="fa fa-check-square-o me-1"></i>Todo</button>
                        <button class="stone-btn stone-btn-clear-all" id="hp-ca"><i class="fa fa-square-o me-1"></i>Limpiar</button>
                    </div>
                    <div class="stone-filter-spacer"></div>
                    <div class="stone-filter-stats"><span id="hp-st" class="stone-filter-stat-loading"><i class="fa fa-circle-o-notch fa-spin me-1"></i>Buscando...</span></div>
                </div>
                <div class="stone-popup-body" id="hp-bd"><div class="stone-empty-state"><i class="fa fa-circle-o-notch fa-spin fa-2x text-muted"></i><div class="stone-empty-text mt-2">Cargando...</div></div></div>
                <div class="stone-popup-footer">
                    <span class="stone-footer-info" id="hp-fi">—</span>
                    <div class="stone-footer-actions">
                        <button class="stone-btn stone-btn-outline" id="hp-cn">Cancelar</button>
                        <button class="stone-btn stone-btn-primary-dark" id="hp-ok2"><i class="fa fa-check me-1"></i>Agregar selección</button>
                    </div>
                </div>
            </div>
        </div>`;

        const ov = root.querySelector("#hp-ov"), bd = root.querySelector("#hp-bd");
        const st = root.querySelector("#hp-st"), fi = root.querySelector("#hp-fi"), bc = root.querySelector("#hp-bc");
        const ps = root.querySelector("#hf-prod");

        const ub = () => { bc.textContent = S.pending.size; };
        const us = () => { st.className = "stone-filter-stat-count"; st.innerHTML = `${S.total} disponibles`; fi.innerHTML = `<strong>${S.quants.length}</strong> de <strong>${S.total}</strong>`; };

        const loadProds = async () => {
            if (!ps) return;
            try {
                const r = await this.orm.searchRead("stock.quant", [["location_id.usage", "=", "internal"], ["quantity", ">", 0], ["lot_id", "!=", false]], ["product_id"], { limit: 500 });
                const seen = new Set(), items = [];
                for (const q of r) { if (q.product_id && !seen.has(q.product_id[0])) { seen.add(q.product_id[0]); items.push({ id: q.product_id[0], name: q.product_id[1] }); } }
                items.sort((a, b) => a.name.localeCompare(b.name));
                for (const p of items) { const o = document.createElement("option"); o.value = p.id; o.textContent = p.name; ps.appendChild(o); }
            } catch (e) { console.error(e); }
        };

        const selAll = () => {
            for (const q of S.quants) { const l = q.lot_id ? q.lot_id[0] : 0; if (l) S.pending.add(l); }
            ub(); bd.querySelectorAll("tr[data-lid]").forEach(tr => { tr.className = "row-sel"; const c = tr.querySelector(".stone-chkbox"); if (c) { c.className = "stone-chkbox checked"; c.innerHTML = '<i class="fa fa-check"></i>'; } const t = tr.querySelector(".stone-tag"); if (t) { t.className = "stone-tag stone-tag-ok"; t.textContent = "Selec."; } });
        };
        const clrAll = () => {
            S.pending.clear(); ub();
            bd.querySelectorAll("tr[data-lid]").forEach(tr => { tr.className = ""; const c = tr.querySelector(".stone-chkbox"); if (c) { c.className = "stone-chkbox"; c.innerHTML = ""; } const t = tr.querySelector(".stone-tag"); if (t) { const rv = tr.dataset.rsv === "1"; t.className = rv ? "stone-tag stone-tag-warn" : "stone-tag stone-tag-free"; t.textContent = rv ? "Reservado" : "Libre"; } });
        };

        const render = () => {
            if (!S.quants.length && !S.loading) { bd.innerHTML = `<div class="stone-empty-state"><i class="fa fa-inbox fa-3x text-muted"></i><div class="stone-empty-text mt-2">Sin resultados</div></div>`; us(); return; }
            let rows = "";
            for (const q of S.quants) {
                const lid = q.lot_id ? q.lot_id[0] : 0, ln = q.lot_id ? q.lot_id[1] : "-";
                const loc = q.location_id ? q.location_id[1].split("/").pop() : "-";
                const sel = S.pending.has(lid), rsv = q.reserved_quantity > 0;
                let badge = `<span class="stone-tag stone-tag-free">Libre</span>`;
                if (sel) badge = `<span class="stone-tag stone-tag-ok">Selec.</span>`;
                else if (rsv) badge = `<span class="stone-tag stone-tag-warn">Reservado</span>`;
                rows += `<tr class="${sel ? "row-sel" : ""}" data-lid="${lid}" data-rsv="${rsv ? "1" : "0"}">
                    <td class="col-chk"><div class="stone-chkbox ${sel ? "checked" : ""}">${sel ? '<i class="fa fa-check"></i>' : ""}</div></td>
                    <td class="cell-lot">${ln}</td><td>${q.x_bloque || "-"}</td><td>${q.x_atado || "-"}</td>
                    <td class="col-num">${q.x_alto ? q.x_alto.toFixed(4) : "-"}</td>
                    <td class="col-num">${q.x_ancho ? q.x_ancho.toFixed(4) : "-"}</td>
                    <td class="col-num">${q.x_grosor || "-"}</td>
                    <td class="col-num fw-semibold">${q.quantity ? q.quantity.toFixed(2) : "-"}</td>
                    <td>${q.x_tipo || "-"}</td><td>${q.x_color || "-"}</td>
                    <td class="cell-loc">${loc}</td><td>${badge}</td></tr>`;
            }
            const sent = `<div id="hp-sn" class="stone-scroll-sentinel">${S.loadingMore ? '<div class="stone-loading-more"><i class="fa fa-circle-o-notch fa-spin me-2"></i>Cargando más...</div>' : ""}${S.hasMore && !S.loadingMore ? '<div class="stone-scroll-hint"><i class="fa fa-chevron-down me-1"></i>Desplázate para más</div>' : ""}</div>`;

            bd.innerHTML = `<table class="stone-popup-table"><thead><tr>
                <th class="col-chk">✓</th><th>Lote</th><th>Bloque</th><th>Atado</th>
                <th class="col-num">Alto</th><th class="col-num">Ancho</th><th class="col-num">Gros.</th>
                <th class="col-num">M²</th><th>Tipo</th><th>Color</th><th>Ubic.</th><th>Estado</th>
                </tr></thead><tbody>${rows}</tbody></table>${sent}`;
            us();

            bd.querySelectorAll("tr[data-lid]").forEach(tr => {
                tr.style.cursor = "pointer";
                tr.addEventListener("click", () => {
                    const lid = parseInt(tr.dataset.lid); if (!lid) return;
                    if (S.pending.has(lid)) S.pending.delete(lid); else S.pending.add(lid);
                    const sel = S.pending.has(lid);
                    tr.className = sel ? "row-sel" : "";
                    const c = tr.querySelector(".stone-chkbox"); if (c) { c.className = "stone-chkbox" + (sel ? " checked" : ""); c.innerHTML = sel ? '<i class="fa fa-check"></i>' : ""; }
                    const t = tr.querySelector(".stone-tag"); if (t) { if (sel) { t.className = "stone-tag stone-tag-ok"; t.textContent = "Selec."; } else { const rv = tr.dataset.rsv === "1"; t.className = rv ? "stone-tag stone-tag-warn" : "stone-tag stone-tag-free"; t.textContent = rv ? "Reservado" : "Libre"; } }
                    ub();
                });
            });

            if (this._popupObserver) { this._popupObserver.disconnect(); this._popupObserver = null; }
            const sn = bd.querySelector("#hp-sn");
            if (sn && S.hasMore) {
                this._popupObserver = new IntersectionObserver(e => { if (e[0].isIntersecting && S.hasMore && !S.loadingMore) load(S.page + 1, false); }, { root: bd, rootMargin: "100px", threshold: 0.1 });
                this._popupObserver.observe(sn);
            }
        };

        const load = async (page, reset) => {
            if (reset) { S.loading = true; S.quants = []; bd.innerHTML = `<div class="stone-empty-state"><i class="fa fa-circle-o-notch fa-spin fa-2x text-muted"></i><div class="stone-empty-text mt-2">Buscando...</div></div>`; st.className = "stone-filter-stat-loading"; st.innerHTML = `<i class="fa fa-circle-o-notch fa-spin me-1"></i>Buscando...`; }
            else S.loadingMore = true;

            try {
                const cur = Array.from(S.pending);
                const d = [["location_id.usage", "=", "internal"], ["quantity", ">", 0], ["lot_id", "!=", false]];
                if (S.productId) d.push(["product_id", "=", S.productId]);
                if (cur.length) { d.push("|"); d.push("&"); d.push(["x_tiene_hold", "=", false]); d.push(["reserved_quantity", "=", 0]); d.push(["lot_id", "in", cur]); }
                else { d.push(["x_tiene_hold", "=", false]); d.push(["reserved_quantity", "=", 0]); }
                if (S.filters.lot_name) d.push(["lot_id.name", "ilike", S.filters.lot_name]);
                if (S.filters.bloque) d.push(["lot_id.x_bloque", "ilike", S.filters.bloque]);
                if (S.filters.atado) d.push(["lot_id.x_atado", "ilike", S.filters.atado]);
                if (S.filters.alto_min) d.push(["lot_id.x_alto", ">=", parseFloat(S.filters.alto_min)]);
                if (S.filters.ancho_min) d.push(["lot_id.x_ancho", ">=", parseFloat(S.filters.ancho_min)]);

                const flds = ["lot_id", "product_id", "location_id", "quantity", "reserved_quantity", "x_grosor", "x_alto", "x_ancho", "x_bloque", "x_atado", "x_tipo", "x_color"];
                const tot = await this.orm.searchCount("stock.quant", d);
                const off = page * PS;
                const qs = await this.orm.searchRead("stock.quant", d, flds, { limit: PS, offset: off, order: "lot_id" });

                if (reset || page === 0) S.quants = qs; else S.quants = [...S.quants, ...qs];
                S.total = tot; S.page = page; S.hasMore = S.quants.length < tot;
            } catch (err) {
                bd.innerHTML = `<div class="stone-empty-state"><i class="fa fa-exclamation-triangle fa-2x text-danger"></i><div class="stone-empty-text mt-2 text-danger">${err.message}</div></div>`;
                return;
            } finally { S.loading = false; S.loadingMore = false; }
            render();
        };

        const confirm = async () => {
            const newIds = Array.from(S.pending);
            this.destroyPopup();
            await this._updateLotsAndM2(newIds);
            await this._refreshDetail();
        };
        const close = () => this.destroyPopup();

        root.querySelector("#hp-x").addEventListener("click", close);
        root.querySelector("#hp-cn").addEventListener("click", close);
        root.querySelector("#hp-ok1").addEventListener("click", confirm);
        root.querySelector("#hp-ok2").addEventListener("click", confirm);
        root.querySelector("#hp-sa").addEventListener("click", selAll);
        root.querySelector("#hp-ca").addEventListener("click", clrAll);
        ov.addEventListener("click", e => { if (e.target === ov) close(); });
        const kd = e => { if (e.key === "Escape") close(); };
        document.addEventListener("keydown", kd); this._popupKeyHandler = kd;

        const sched = () => { if (timer) clearTimeout(timer); timer = setTimeout(() => load(0, true), 350); };
        const bf = (id, k) => { const i = root.querySelector(`#${id}`); if (i) i.addEventListener("input", e => { S.filters[k] = e.target.value; sched(); }); };
        bf("hf-lot", "lot_name"); bf("hf-blq", "bloque"); bf("hf-ata", "atado"); bf("hf-alt", "alto_min"); bf("hf-anc", "ancho_min");
        if (ps) ps.addEventListener("change", e => { S.productId = e.target.value ? parseInt(e.target.value) : 0; load(0, true); });

        loadProds().then(() => load(0, true));
    }

    destroyPopup() {
        if (this._popupObserver) { this._popupObserver.disconnect(); this._popupObserver = null; }
        if (this._popupKeyHandler) { document.removeEventListener("keydown", this._popupKeyHandler); this._popupKeyHandler = null; }
        if (this._popupRoot) { this._popupRoot.remove(); this._popupRoot = null; }
    }
}

HoldStoneButton.template = "stock_lot_dimensions.HoldStoneButton";
registry.category("fields").add("hold_stone_button", { component: HoldStoneButton, displayName: "Botón Selección Piedra (Hold)" });