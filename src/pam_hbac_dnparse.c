/*
    Copyright (C) 2015 Jakub Hrozek <jakub.hrozek@posteo.se>

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU Lesser General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#define _GNU_SOURCE     /* strndup() */

#include <string.h>
#include <ctype.h>
#include <stdbool.h>
#include <errno.h>
#include <ldap.h>

#include "pam_hbac_dnparse.h"
#include "pam_hbac_compat.h"

/* if val is NULL, only key is checked */
static bool
rdn_keyval_matches(LDAPAVA **rdn, const char *key, const char *val)
{
    bool matches = false;

    if (rdn != NULL && rdn[0] != NULL && rdn[1] == NULL) {
        /* Exactly one value */
        if (strncasecmp(rdn[0]->la_attr.bv_val, key,
                        rdn[0]->la_attr.bv_len) == 0) {
            /* The key matches */
            if (val == NULL ||
                strncasecmp(rdn[0]->la_value.bv_val, val,
                            rdn[0]->la_value.bv_len) == 0) {
                /* The value matches */
                matches = true;
            }
        }
    }

    return matches;
}

static bool
dn_matches(LDAPAVA *dn, LDAPAVA *dn2)
{
    if (dn == NULL || dn2 == NULL) {
        return false;
    }

    if (dn->la_attr.bv_len != dn2->la_attr.bv_len) {
        return false;
    }

    if (dn->la_value.bv_len != dn2->la_value.bv_len) {
        return false;
    }

    if (strncasecmp(dn->la_attr.bv_val,
                    dn2->la_attr.bv_val,
                    dn->la_attr.bv_len) != 0) {
        return false;
    }

    if (strncasecmp(dn->la_value.bv_val,
                    dn2->la_value.bv_val,
                    dn->la_value.bv_len) != 0) {
        return false;
    }

    return true;
}

static char *
rdn_check_and_getval(LDAPAVA **rdn, const char *key)
{
    char *rdn_val = NULL;

    if (rdn != NULL && rdn[0] != NULL && rdn[1] == NULL) {
        /* Exactly one value */
        if (strncasecmp(rdn[0]->la_attr.bv_val, key,
                        rdn[0]->la_attr.bv_len) == 0) {
            /* The key matches */
            rdn_val = strndup(rdn[0]->la_value.bv_val,
                              rdn[0]->la_value.bv_len);
        }
    }

    /* NULL check should be done by the caller anyway */
    return rdn_val;
}

static bool
basedn_matches(const char *basedn, LDAPDN dn_parts)
{
    LDAPDN basedn_parts = NULL;
    size_t i = 0;
    int ret;

    ret = ph_str2dn(basedn, &basedn_parts);
    if (ret != 0) {
        goto fail;
    }

    for (i=0; dn_parts[i] != NULL; i++) {

        if (basedn_parts[i] == NULL) {
            goto fail;
        }

        if (!dn_matches(*dn_parts[i], *basedn_parts[i])) {
            goto fail;
        }
    }

    /* Base DN must have be matched completely. */
    if (basedn_parts[i] != NULL) {
        goto fail;
    }

    ph_ldap_dnfree(basedn_parts);
    return true;

fail:
    ph_ldap_dnfree(basedn_parts);
    return false;
}

static bool
container_matches(LDAPDN dn_parts, const char *basedn, const char ***kvs)
{
    size_t idx;
    bool match;

    if (dn_parts == NULL || basedn == NULL || kvs == NULL) {
        return false;
    }

    for (idx = 0; kvs[idx]; idx++) {
        /* +1 because we don't care about RDN value, only the remainder */
        if (dn_parts[idx+1] == NULL) {
            /* Short DN.. */
            return false;
        }

        match = rdn_keyval_matches(dn_parts[idx+1], kvs[idx][0], kvs[idx][1]);
        if (match == false) {
            return false;
        }
    }

    if (!basedn_matches(basedn, &dn_parts[idx + 1])) {
        return false;
    }

    return true;
}

static int
container_check_and_get_rdn(LDAPDN dn_parts,
                            const char *basedn,
                            const char ***container_kvs,
                            const char *rdn_key,
                            const char **_rdn_val)
{
    bool ok;

    ok = container_matches(dn_parts, basedn, container_kvs);
    if (!ok) {
        /* FIXME - This return code sucks */
        return EINVAL;
    }

    if (dn_parts[0] == NULL) {
        return ERANGE;
    }
    *_rdn_val = rdn_check_and_getval(dn_parts[0], rdn_key);
    if (*_rdn_val == NULL) {
        return EINVAL;
    }

    return 0;
}

static int
user_container_rdn(LDAPDN dn_parts,
                   const char *basedn,
                   const char **_rdn_val)
{
    const char *cn1[] = { "cn", "users" };
    const char *cn2[] = { "cn", "accounts" };
    const char **group_container[] = {
        cn1, cn2, NULL
    };

   return container_check_and_get_rdn(dn_parts, basedn, group_container,
                                       "uid", _rdn_val);
}

static int
usergroup_container_rdn(LDAPDN dn_parts,
                        const char *basedn,
                        const char **_rdn_val)
{
    const char *cn1[] = { "cn", "groups" };
    const char *cn2[] = { "cn", "accounts" };
    const char **group_container[] = {
        cn1, cn2, NULL
    };

    return container_check_and_get_rdn(dn_parts, basedn, group_container,
                                       "cn",_rdn_val);
}

static int
svc_container_rdn(LDAPDN dn_parts,
                  const char *basedn,
                  const char **_rdn_val)
{
    const char *cn1[] = { "cn", "hbacservices" };
    const char *cn2[] = { "cn", "hbac" };
    const char **svc_container[] = {
        cn1, cn2, NULL
    };

    return container_check_and_get_rdn(dn_parts, basedn, svc_container,
                                       "cn", _rdn_val);
}

static int
svcgroup_container_rdn(LDAPDN dn_parts,
                       const char *basedn,
                       const char **_rdn_val)
{
    const char *cn1[] = { "cn", "hbacservicegroups" };
    const char *cn2[] = { "cn", "hbac" };
    const char **svc_container[] = {
        cn1, cn2, NULL
    };

    return container_check_and_get_rdn(dn_parts, basedn, svc_container,
                                       "cn", _rdn_val);
}

static int
host_container_rdn(LDAPDN dn_parts,
                   const char *basedn,
                   const char **_rdn_val)
{
    const char *cn1[] = { "cn", "computers" };
    const char *cn2[] = { "cn", "accounts" };
    const char **host_container[] = {
        cn1, cn2, NULL
    };

    return container_check_and_get_rdn(dn_parts, basedn, host_container,
                                       "fqdn", _rdn_val);
}

static int
hostgroup_container_rdn(LDAPDN dn_parts,
                        const char *basedn,
                        const char **_rdn_val)
{
    const char *cn1[] = { "cn", "hostgroups" };
    const char *cn2[] = { "cn", "accounts" };
    const char **host_container[] = {
        cn1, cn2, NULL
    };

    return container_check_and_get_rdn(dn_parts, basedn, host_container,
                                       "cn", _rdn_val);
}

int
ph_group_name_from_dn(const char *dn,
                      enum member_el_type el_type,
                      const char *basedn,
                      const char **_group_name)
{
    LDAPDN dn_parts;
    int ret;

    ret = ph_str2dn(dn, &dn_parts);
    if (ret != 0) {
        return EINVAL;
    }

    switch (el_type) {
    case DN_TYPE_USER:
        ret = usergroup_container_rdn(dn_parts, basedn, _group_name);
        break;
    case DN_TYPE_SVC:
        ret = svcgroup_container_rdn(dn_parts, basedn, _group_name);
        break;
    case DN_TYPE_HOST:
        ret = hostgroup_container_rdn(dn_parts, basedn, _group_name);
        break;
    default:
        ret = EINVAL;
        break;
    }

    ph_ldap_dnfree(dn_parts);
    return ret;
}

int
ph_name_from_dn(const char *dn,
                enum member_el_type el_type,
                const char *basedn,
                const char **_name)
{
    LDAPDN dn_parts;
    int ret;

    ret = ph_str2dn(dn, &dn_parts);
    if (ret != 0) {
        return EINVAL;
    }

    switch (el_type) {
    case DN_TYPE_USER:
        ret = user_container_rdn(dn_parts, basedn, _name);
        break;
    case DN_TYPE_SVC:
        ret = svc_container_rdn(dn_parts, basedn, _name);
        break;
    case DN_TYPE_HOST:
        ret = host_container_rdn(dn_parts, basedn, _name);
        break;
    default:
        ret = EINVAL;
        break;
    }

    ph_ldap_dnfree(dn_parts);
    return ret;
}

const char *
ph_member_el_type2str(const enum member_el_type el_type)
{
    switch (el_type) {
    case DN_TYPE_USER:
        return "user";
    case DN_TYPE_SVC:
        return "service";
    case DN_TYPE_HOST:
        return "host";
    default:
        break;
    }

    return "unknown";
}
