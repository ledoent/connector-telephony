/*
    Copyright 2025 Dixmit
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/
import {PhoneField} from "@web/views/fields/phone/phone_field";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";

patch(PhoneField.prototype, {
    setup() {
        super.setup();
        this.agent = useService("voip_agent_oca");
    },
    /**
     * Place the call through the softphone when an agent is registered.
     *
     * 20.0 rebuilt this field: the markup is driven by `actionButtons`, whose
     * single "Call" entry invokes this hook, and its anchor already carries
     * `t-on-click.prevent.stop`. There is no longer an `<a class="o_form_uri">`
     * -- nor a `web.FormPhoneField` template -- to xpath onto, so the
     * `voip.PhoneField` / `voip.FormPhoneField` extensions were dropped rather
     * than re-pointed.
     *
     * Falling through to `super()` when no agent is registered preserves the
     * 19.0 behaviour: there, returning early let the browser follow the `tel:`
     * href. Here the click is always prevented, so the base implementation has
     * to be invoked explicitly or the button would do nothing without voip.
     */
    onLinkClicked() {
        if (!this.agent.agent) {
            return super.onLinkClicked();
        }
        return this.agent.call({number: this.dialNumber});
    },
});
