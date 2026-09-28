/** @odoo-module **/
// LISTA DE ÓRDENES DE RESERVA — celdas visuales (27 sep 2026).
//
// - som_hold_status (x_estatus_reserva): píldora de color con ícono y, debajo,
//   la cuenta regresiva ("vence hoy", "vence en 3 días", "venció el 25 sep")
//   o la SO si ya se convirtió.
// - som_hold_auth (x_price_auth_status): píldora con escudo del estatus de la
//   solicitud de autorización de precio; vacío = guion tenue.
// - som_date_cell: fechas con el formato único del sistema ("28 sep 2026").
//   Los datetime llegan como luxon en la zona del usuario: se usan sus
//   componentes locales (nunca UTC → nunca "el día anterior").
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

function fmtDay(dt, withYear = true) {
    if (!dt || !dt.isValid) {
        return "";
    }
    return withYear ? `${dt.day} ${MESES[dt.month - 1]} ${dt.year}` : `${dt.day} ${MESES[dt.month - 1]}`;
}

function daysUntil(dt) {
    if (!dt || !dt.isValid) {
        return null;
    }
    const today = luxon.DateTime.local().startOf("day");
    return Math.round(dt.startOf("day").diff(today, "days").days);
}

function m2oName(value) {
    if (!value) {
        return "";
    }
    if (Array.isArray(value)) {
        return value[1] || "";
    }
    return value.display_name || "";
}

const STATUS = {
    vigente: { label: "Vigente", cls: "ok", icon: "fa-check-circle" },
    borrador: { label: "Borrador", cls: "draft", icon: "fa-pencil" },
    vencida: { label: "Vencida", cls: "danger", icon: "fa-clock-o" },
    en_so: { label: "En venta", cls: "info", icon: "fa-shopping-cart" },
    finalizada: { label: "Finalizada", cls: "muted", icon: "fa-flag-checkered" },
    cancelada: { label: "Cancelada", cls: "muted", icon: "fa-ban" },
};

export class SomHoldStatusCell extends Component {
    static template = "stock_lot_dimensions.SomHoldStatusCell";
    static props = { ...standardFieldProps };

    get value() {
        return this.props.record.data[this.props.name];
    }

    get cfg() {
        return STATUS[this.value] || { label: this.value || "", cls: "muted", icon: "fa-circle-o" };
    }

    /** Segunda línea: cuenta regresiva o SO. {text, cls} */
    get hint() {
        const data = this.props.record.data;
        const exp = data.fecha_expiracion;
        if (this.value === "en_so") {
            const so = m2oName(data.sale_order_id);
            return so ? { text: so, cls: "" } : null;
        }
        if (this.value === "vencida") {
            return exp ? { text: `venció el ${fmtDay(exp, false)}`, cls: "danger" } : null;
        }
        if (this.value === "vigente" || this.value === "borrador") {
            const d = daysUntil(exp);
            if (d === null) {
                return null;
            }
            if (d < 0) {
                return { text: "vencimiento pasado", cls: "danger" };
            }
            if (d === 0) {
                return { text: "vence hoy", cls: "danger" };
            }
            if (d === 1) {
                return { text: "vence mañana", cls: "warn" };
            }
            return { text: `vence en ${d} días`, cls: d <= 3 ? "warn" : "" };
        }
        return null;
    }
}

const AUTH = {
    required: { label: "Por solicitar", cls: "danger", icon: "fa-exclamation-circle" },
    pending: { label: "Pendiente", cls: "warn", icon: "fa-hourglass-half" },
    approved: { label: "Autorizada", cls: "ok", icon: "fa-shield" },
    rejected: { label: "Rechazada", cls: "danger", icon: "fa-times-circle" },
    expired: { label: "Expirada", cls: "muted", icon: "fa-shield" },
};

export class SomHoldAuthCell extends Component {
    static template = "stock_lot_dimensions.SomHoldAuthCell";
    static props = { ...standardFieldProps };

    get cfg() {
        return AUTH[this.props.record.data[this.props.name]] || null;
    }
}

export class SomDateCell extends Component {
    static template = "stock_lot_dimensions.SomDateCell";
    static props = { ...standardFieldProps };

    get text() {
        return fmtDay(this.props.record.data[this.props.name]);
    }
}

registry.category("fields").add("som_hold_status", {
    component: SomHoldStatusCell,
    supportedTypes: ["selection"],
    additionalClasses: ["o_som_hold_status_cell"],
});
registry.category("fields").add("som_hold_auth", {
    component: SomHoldAuthCell,
    supportedTypes: ["selection"],
});
registry.category("fields").add("som_date_cell", {
    component: SomDateCell,
    supportedTypes: ["date", "datetime"],
});
