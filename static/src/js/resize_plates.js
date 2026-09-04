/** @odoo-module **/
// Redimensionamiento de placas — client action de Inventario/Operaciones.
// Selector visual de placas de la casa (agrupado por bloque, fotos,
// dimensiones) especializado: cada fila editable (nuevo alto × ancho) y
// barra de lote para aplicar dimensiones a toda la selección.
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";

export class ResizePlates extends Component {
    static template = "stock_lot_dimensions.ResizePlates";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            productQuery: "",
            productOptions: [],
            product: null,
            // Búsqueda por LOTE: opciones del servidor y filtro sobre la
            // cuadrícula cargada (texto libre, coincidencia parcial).
            lotQuery: "",
            lotOptions: [],
            lotFilter: "",
            loading: false,
            plates: [],
            // ediciones por lot_id: { alto, ancho }
            edits: {},
            selected: {},
            batchAlto: "",
            batchAncho: "",
            applying: false,
        });
        this._searchTimer = null;
    }

    // ── Buscador de producto ──
    onProductQuery(ev) {
        this.state.productQuery = ev.target.value;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.searchProducts(), 250);
    }

    async searchProducts() {
        const q = (this.state.productQuery || "").trim();
        if (q.length < 2) {
            this.state.productOptions = [];
            return;
        }
        const res = await this.orm.call("product.product", "name_search", [], {
            name: q,
            domain: [["type", "=", "consu"]],
            limit: 12,
        });
        this.state.productOptions = res.map(([id, name]) => ({ id, name }));
    }

    async pickProduct(opt) {
        this.state.product = opt;
        this.state.productOptions = [];
        this.state.productQuery = opt.name;
        this.state.lotFilter = "";
        await this.loadPlates();
    }

    // ── Buscador por lote (cualquier producto con stock interno) ──
    onLotQuery(ev) {
        this.state.lotQuery = ev.target.value;
        // Si ya hay placas cargadas, el mismo texto filtra la cuadrícula.
        this.state.lotFilter = this.state.product ? this.state.lotQuery : "";
        clearTimeout(this._lotTimer);
        this._lotTimer = setTimeout(() => this.searchLots(), 250);
    }

    async searchLots() {
        const q = (this.state.lotQuery || "").trim();
        if (q.length < 2) {
            this.state.lotOptions = [];
            return;
        }
        try {
            this.state.lotOptions = await this.orm.call("stock.lot", "slr_search_lots", [q]);
        } catch (e) {
            this.state.lotOptions = [];
        }
    }

    async pickLot(opt) {
        this.state.lotOptions = [];
        this.state.lotQuery = opt.lot_name;
        if (!this.state.product || this.state.product.id !== opt.product_id) {
            this.state.product = { id: opt.product_id, name: opt.product_name };
            this.state.productQuery = opt.product_name;
            this.state.productOptions = [];
            await this.loadPlates();
        }
        this.state.lotFilter = opt.lot_name;
    }

    clearLotFilter() {
        this.state.lotFilter = "";
        this.state.lotQuery = "";
        this.state.lotOptions = [];
    }

    // Placas visibles: las cargadas del producto, acotadas por el filtro
    // de lote (coincidencia parcial, sin distinguir mayúsculas).
    get visiblePlates() {
        const f = (this.state.lotFilter || "").trim().toUpperCase();
        if (!f) {
            return this.state.plates;
        }
        return this.state.plates.filter((p) => (p.lot_name || "").toUpperCase().includes(f));
    }

    async loadPlates() {
        if (!this.state.product) {
            return;
        }
        this.state.loading = true;
        this.state.edits = {};
        this.state.selected = {};
        try {
            this.state.plates = await this.orm.call(
                "stock.lot", "slr_get_plates", [this.state.product.id]
            );
        } catch (e) {
            this.notification.add(
                (e && e.data && e.data.message) || "No se pudieron cargar las placas.",
                { type: "danger" }
            );
            this.state.plates = [];
        } finally {
            this.state.loading = false;
        }
    }

    // ── Agrupado por bloque (mismo lenguaje del selector de ventas/hold) ──
    get groups() {
        const map = new Map();
        for (const p of this.visiblePlates) {
            if (!map.has(p.bloque)) {
                map.set(p.bloque, []);
            }
            map.get(p.bloque).push(p);
        }
        return [...map.entries()].map(([name, plates]) => ({ name, plates }));
    }

    // ── Selección ──
    toggle(p) {
        if (this.state.selected[p.lot_id]) {
            delete this.state.selected[p.lot_id];
        } else {
            this.state.selected[p.lot_id] = true;
        }
    }

    toggleAll() {
        if (this.selCount === this.visiblePlates.length) {
            this.state.selected = {};
        } else {
            const s = {};
            for (const p of this.visiblePlates) {
                s[p.lot_id] = true;
            }
            this.state.selected = s;
        }
    }

    get selCount() {
        return Object.keys(this.state.selected).length;
    }

    // ── Edición de dimensiones ──
    edit(p, field, ev) {
        const v = ev.target.value;
        const e = this.state.edits[p.lot_id] || { alto: "", ancho: "" };
        e[field] = v;
        this.state.edits = { ...this.state.edits, [p.lot_id]: e };
    }

    newVal(p, field) {
        const e = this.state.edits[p.lot_id];
        return e && e[field] !== "" && e[field] != null ? e[field] : "";
    }

    newM2(p) {
        const e = this.state.edits[p.lot_id];
        if (!e) {
            return null;
        }
        const a = parseFloat(e.alto !== "" ? e.alto : p.alto);
        const w = parseFloat(e.ancho !== "" ? e.ancho : p.ancho);
        if (!isFinite(a) || !isFinite(w) || a <= 0 || w <= 0) {
            return null;
        }
        return a * w;
    }

    applyBatch() {
        const a = this.state.batchAlto;
        const w = this.state.batchAncho;
        if (a === "" && w === "") {
            return;
        }
        const edits = { ...this.state.edits };
        for (const lotId of Object.keys(this.state.selected)) {
            const e = edits[lotId] || { alto: "", ancho: "" };
            if (a !== "") {
                e.alto = a;
            }
            if (w !== "") {
                e.ancho = w;
            }
            edits[lotId] = e;
        }
        this.state.edits = edits;
    }

    get changes() {
        const out = [];
        for (const p of this.state.plates) {
            const e = this.state.edits[p.lot_id];
            if (!e) {
                continue;
            }
            const alto = e.alto !== "" ? parseFloat(e.alto) : p.alto;
            const ancho = e.ancho !== "" ? parseFloat(e.ancho) : p.ancho;
            if (!isFinite(alto) || !isFinite(ancho)) {
                continue;
            }
            if (Math.abs(alto - p.alto) > 0.0005 || Math.abs(ancho - p.ancho) > 0.0005) {
                out.push({ lot_id: p.lot_id, alto, ancho, name: p.lot_name });
            }
        }
        return out;
    }

    async apply() {
        const ch = this.changes;
        if (!ch.length) {
            this.notification.add("No hay cambios de dimensiones capturados.", { type: "warning" });
            return;
        }
        this.state.applying = true;
        try {
            const res = await this.orm.call("stock.lot", "slr_apply_resizes", [
                ch.map(({ lot_id, alto, ancho }) => ({ lot_id, alto, ancho })),
            ]);
            this.notification.add(res.message, { type: res.ok ? "success" : "warning" });
            if (res.ok) {
                await this.loadPlates();
                this.state.batchAlto = "";
                this.state.batchAncho = "";
            }
        } catch (e) {
            this.notification.add(
                (e && e.data && e.data.message) || "No se pudo aplicar el redimensionamiento.",
                { type: "danger" }
            );
        } finally {
            this.state.applying = false;
        }
    }

    get totalM2() {
        return this.visiblePlates.reduce((a, p) => a + (p.m2 || 0), 0);
    }

    // Las plantillas OWL no exponen Math: el resaltado de m² cambiado se
    // decide aquí (Math.abs en el XML tumbaba la pantalla al capturar).
    isChanged(p) {
        const m2 = this.newM2(p);
        return m2 !== null && Math.abs(m2 - p.m2) > 0.0005;
    }

    fmt(n) {
        return (n || n === 0) ? Number(n).toFixed(2) : "—";
    }
}

registry.category("actions").add("stock_lot_dimensions.resize_plates", ResizePlates);
