/*
    Copyright 2025 Dixmit
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/
import {Component, proxy} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

export class VoipOCASystray extends Component {
    static template = "voip_oca.VoipOCASystray";
    setup() {
        this.voip_oca = proxy(useService("voip_oca"));
    }
    onClick() {
        this.voip_oca.handleVoip();
    }
}
registry.category("systray").add("voip_systray_oca", {Component: VoipOCASystray});
