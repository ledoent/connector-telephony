/*
    Copyright 2025 Dixmit
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/

import {Component, onMounted, t, useProps} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

export class PartnerList extends Component {
    static template = "voip_oca.PartnerList";
    props = useProps({records: t.array()});
    setup() {
        super.setup();
        this.voip = useService("voip_oca");
        onMounted(() => this.voip.searchPartners());
    }

    onClick(partner) {
        this.voip.open({partner});
    }
}

registry.category("voip_elements").add("partner_list", {
    component: PartnerList,
    order: 30,
    title: _t("Contacts"),
    input: "partners",
    search: (voip, value) => voip.searchPartners(value),
    call: (voip) => {
        if (voip.partners) {
            voip.open({partner: voip.partners[0]});
        }
    },
});
