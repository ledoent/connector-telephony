/*
    Copyright 2025 Dixmit
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/
import {Component, onMounted, proxy, signal, t, useProps} from "@odoo/owl";
import {useSelection} from "@mail/utils/common/hooks";
import {useService} from "@web/core/utils/hooks";

export class Numpad extends Component {
    static template = "voip_oca.Numpad";
    // Owl 3 folds defaultProps into the schema: .optional(<factory>).
    props = useProps({
        // eslint-disable-next-line no-empty-function
        onNumpadValue: t.function().optional(() => () => {}),
        // eslint-disable-next-line no-empty-function
        onCall: t.function().optional(() => () => {}),
    });
    numpadValue = signal.ref();
    setup() {
        super.setup();
        this.keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];
        this.voip = proxy(useService("voip_oca"));
        // Ref declared as a class field below; signal.ref() is the Owl 3 form.
        this.selectionNumpad = useSelection({
            ref: this.numpadValue,
            model: this.voip.numpad.selection,
        });
        onMounted(() => this.numpadValue()?.focus());
    }

    onKeyClick(key) {
        const {value} = this.voip.numpad;
        const {selectionStart, selectionEnd} = this.numpadValue();
        this.voip.numpad.value =
            value.slice(0, selectionStart) + key + value.slice(selectionEnd);
        this.numpadValue().focus();
        this.selectionNumpad.restore();
        this.onNumpadValue({key});
    }

    onNumpadValue(ev) {
        const {value} = this.voip.numpad;
        if (ev.key === "Enter" && value.length > 0) {
            this.props.onCall();
            return;
        }
        this.props.onNumpadValue(ev.key);
    }

    deleteNumber() {
        const {value} = this.voip.numpad;
        if (value.length > 0) {
            this.voip.numpad.value = value.slice(0, -1);
        }
    }
}
