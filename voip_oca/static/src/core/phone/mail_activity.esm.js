import {Activity} from "@mail/core/common/activity_model";
import {assignIn} from "@mail/utils/common/misc";
import {patch} from "@web/core/utils/patch";

patch(Activity, {
    _insert(data) {
        const activity = super._insert(...arguments);
        assignIn(activity, data, ["main_partner_id", "main_partner"]);
        return activity;
    },
});
