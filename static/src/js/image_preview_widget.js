/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ImagePreviewWidget extends Component {
    setup() {
        this.state = useState({
            showModal: false,
        });
    }

    get imageUrl() {
        if (!this.props.value) {
            return null;
        }
        // El valor viene como base64, lo convertimos a data URL
        return `data:image/png;base64,${this.props.value}`;
    }

    openPreview(ev) {
        // Prevenir que se abra el registro
        ev.stopPropagation();
        ev.preventDefault();
        
        if (this.props.value) {
            this.state.showModal = true;
        }
    }

    closePreview() {
        this.state.showModal = false;
    }
}

ImagePreviewWidget.template = "stock_lot_dimensions.ImagePreviewWidget";

registry.category("fields").add("image_preview_clickable", {
    component: ImagePreviewWidget,
});