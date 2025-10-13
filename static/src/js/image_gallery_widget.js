/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ImageGalleryWidget extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            images: [],
            currentIndex: 0,
            showModal: false,
        });
        this.loadImages();
    }

    async loadImages() {
        if (this.props.value) {
            const lotId = this.props.value;
            const images = await this.orm.searchRead(
                "stock.lot.image",
                [["lot_id", "=", lotId]],
                ["id", "name", "image", "sequence"],
                { order: "sequence, id" }
            );
            this.state.images = images;
        }
    }

    openGallery(index) {
        this.state.currentIndex = index;
        this.state.showModal = true;
    }

    closeGallery() {
        this.state.showModal = false;
    }

    nextImage() {
        if (this.state.currentIndex < this.state.images.length - 1) {
            this.state.currentIndex++;
        }
    }

    prevImage() {
        if (this.state.currentIndex > 0) {
            this.state.currentIndex--;
        }
    }

    getImageUrl(imageId) {
        return `/web/image/stock.lot.image/${imageId}/image`;
    }
}

ImageGalleryWidget.template = "stock_lot_dimensions.ImageGalleryWidget";

registry.category("fields").add("image_gallery", {
    component: ImageGalleryWidget,
});
