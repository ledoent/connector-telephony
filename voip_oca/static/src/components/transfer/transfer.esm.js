/*
    Copyright 2025 Dixmit
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/

import {Component, onMounted, proxy, signal, t, useProps} from "@odoo/owl";

export class Transfer extends Component {
    static template = "voip_oca.Transfer";
    props = useProps({
        onTransfer: t.function(),
        close: t.function(),
    });
    inputRef = signal.ref();
    setup() {
        // Ref declared as a class field below; signal.ref() is the Owl 3 form.
        this.state = proxy({value: ""});
        onMounted(() => this.inputRef()?.focus());
    }
    onKeydown(ev) {
        if (ev.key === "Escape") {
            this.props.close();
        }
        if (ev.key === "Enter") {
            this.transfer();
        }
    }
    transfer() {
        this.props.onTransfer(this.state.value);
        this.props.close();
    }
}
