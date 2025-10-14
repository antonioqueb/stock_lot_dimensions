/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class StatusIconsWidget extends Component {
    static template = "stock_lot_dimensions.StatusIconsWidget";
    static supportedTypes = ["char"];

    setup() {
        this.notification = useService("notification");
    }

    get estados() {
        const data = this.props.record.data;
        return {
            reservado: data.x_esta_reservado || false,
            entrega: data.x_en_orden_entrega || false,
            detalles: data.x_tiene_detalles || false,
            textoDetalles: data.x_detalles_placa || 'Sin detalles'
        };
    }

    mostrarDetalles(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        this.notification.add(this.estados.textoDetalles, {
            title: "Detalles de la Placa",
            type: "info",
        });
    }
}

registry.category("fields").add("status_icons", {
    component: StatusIconsWidget,
});