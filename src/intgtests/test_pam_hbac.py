#!/usr/bin/env python

import unittest
import os
import shutil
import ssl
import urllib
import urllib2
import json

from cookielib import CookieJar

import pypamtest


class IpaClientlessTestDriver(object):
    def __init__(self,
                 hostname, domain, password,
                 bind_dn, bind_pw,
                 username='admin', insecure=False):
        self.hostname = hostname
        self.domain = domain
        self.password = password
        self.username = username
        self.bind_dn = bind_dn
        self.bind_pw = bind_pw
        self.referer = "https://" + self.hostname + "/ipa"

        self.cj = CookieJar()
        self.ssl_ctx = self._ssl_ctx(insecure)

    def _auth(self, lazy=True):
        if lazy is True and len(self.cj) > 0:
            return 200

        login_url = self.referer + "/session/login_password"

        request = urllib2.Request(login_url)
        request.add_header('referer', self.referer)
        request.add_header('Content-Type', 'application/x-www-form-urlencoded')
        request.add_header('Accept', 'text/plain')

        query_args = {'user': self.username,
                      'password': self.password}
        encoded_args = urllib.urlencode(query_args)

        result = urllib2.urlopen(request,
                                 encoded_args,
                                 context=self.ssl_ctx)
        if result.getcode() == 200:
            self.cj.extract_cookies(result, request)
        return result.getcode()

    def _ssl_ctx(self, insecure):
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _json_request(self, jdata):
        ret = self._auth()
        if ret != 200:
            return ret

        json_url = self.referer + "/session/json"
        request = urllib2.Request(json_url)

        request.add_header('referer', self.referer)
        request.add_header('Content-Type', 'application/json')
        request.add_header('Accept', 'application/json')

        self.cj.add_cookie_header(request)
        result = urllib2.urlopen(request,
                                 jdata,
                                 context=self.ssl_ctx)
        return result.getcode()

    def fetch_cert(self, dest):
        url = "http://" + self.hostname + "/ipa/config/ca.crt"
        self.ca_cert = os.path.join(dest, "ca.crt")
        urllib.urlretrieve(url, self.ca_cert)

    def rm_cert(self):
        os.unlink(self.ca_cert)

    def run_cmd(self, method, params, args={}):
        cmd = json.dumps({"method": method,
                          "params": [params, args],
                          "id": "0"})
        return self._json_request(cmd)


class IpaClientlessPamHbacHost(object):
    def __init__(self, driver, name):
        self.driver = driver
        self.name = "%s.%s" % (name, self.driver.domain)

    def add(self):
        args = dict()
        args['force'] = 'true'
        self.driver.run_cmd("host_add", [self.name], args)

    def remove(self):
        self.driver.run_cmd("host_del", [self.name])


class IpaClientlessPamHbacHostGroup(object):
    def __init__(self, driver, name):
        self.driver = driver
        self.name = name

    def add(self):
        self.driver.run_cmd("hostgroup_add", [self.name])

    def remove(self):
        self.driver.run_cmd("hostgroup_del", [self.name])

    def add_member(self, host=None, hostgroup=None):
        args = dict()
        if host:
            args['host'] = [host]
        if hostgroup:
            args['hostgroup'] = [hostgroup]
        self.driver.run_cmd("hostgroup_add_member", [self.name], args)


class IpaClientlessPamHbacUser(object):
    def __init__(self, driver, name):
        self.driver = driver
        self.name = name

    def add(self, first=None, last=None):
        args = dict()
        if not first:
            first = self.name
        if not last:
            last = self.name

        args['cn'] = "%s %s" % (first, last)
        args['displayname'] = "%s %s" % (first, last)
        args['gecos'] = "%s %s" % (first, last)
        args['givenname'] = first
        args['sn'] = last
        args['initials'] = "%s%s" % (first[0], last[0])
        args['krbprincipalname'] = "%s@%s" % (self.name,
                                              self.driver.domain.upper())
        args['noprivate'] = 'false'
        args['random'] = 'false'

        self.driver.run_cmd("user_add", [self.name], args)

    def remove(self):
        self.driver.run_cmd("user_del", [self.name])


class IpaClientlessPamHbacUserGroup(object):
    def __init__(self, driver, name):
        self.driver = driver
        self.name = name

    def add(self):
        self.driver.run_cmd("group_add", [self.name])

    def remove(self):
        self.driver.run_cmd("group_del", [self.name])

    def add_member(self, user=None, group=None):
        args = dict()
        if user:
            args['user'] = [user]
        if user:
            args['group'] = [group]
        self.driver.run_cmd("group_add_member", [self.name], args)


class IpaClientlessPamHbacService(object):
    def __init__(self, driver, name):
        self.driver = driver
        self.name = name

    def add(self):
        self.driver.run_cmd("hbacsvc_add", [self.name])

    def remove(self):
        self.driver.run_cmd("hbacsvc_del", [self.name])


class IpaClientlessPamHbacServiceGroup(object):
    def __init__(self, driver, name):
        self.driver = driver
        self.name = name

    def add(self):
        self.driver.run_cmd("hbacsvcgroup_add", [self.name])

    def remove(self):
        self.driver.run_cmd("hbacsvcgroup_del", [self.name])

    def add_member(self, svc):
        args = dict()
        args['hbacsvc'] = [svc]
        self.driver.run_cmd("hbacsvcgroup_add_member", [self.name], args)


class IpaClientlessPamHbacRule(object):
    def __init__(self, driver, name):
        self.driver = driver
        self.name = name

    def add(self):
        self.driver.run_cmd("hbacrule_add", [self.name])

    def remove(self):
        self.driver.run_cmd("hbacrule_del", [self.name])

    def add_svc(self, svc=None, svcgroup=None):
        args = dict()
        if svc:
            args['hbacsvc'] = [svc]
        if svcgroup:
            args['hbacsvcgroup'] = [svcgroup]
        self.driver.run_cmd("hbacrule_add_service", [self.name], args)

    def add_user(self, user=None, usergroup=None):
        args = dict()
        if user:
            args['user'] = [user]
        if usergroup:
            args['group'] = [usergroup]
        self.driver.run_cmd("hbacrule_add_user", [self.name], args)

    def add_host(self, host=None, hostgroup=None):
        args = dict()
        if host:
            args['host'] = [host]
        if hostgroup:
            args['hostgroup'] = [hostgroup]
        self.driver.run_cmd("hbacrule_add_host", [self.name], args)

    def enable(self):
        self.driver.run_cmd("hbacrule_enable", [self.name])

    def disable(self):
        self.driver.run_cmd("hbacrule_disable", [self.name])

    def add_all_cats(self):
        args = dict()
        args['usercategory'] = ['all']
        args['hostcategory'] = ['all']
        args['servicecategory'] = ['all']
        self.driver.run_cmd("hbacrule_mod", [self.name], args)


class PamHbacTestCase(unittest.TestCase):
    def setUp(self):
        self._pwrap_setup()
        self._driver_setup()
        self.driver.fetch_cert(self.pwrap_runtimedir)

        self.client_shortname = "pamhbacclient"
        self.client_hostname = "pamhbacclient" + "." + self.driver.domain
        self.host = IpaClientlessPamHbacHost(self.driver,
                                             self.client_shortname)
        self.host.add()

    def tearDown(self):
        self.host.remove()
        self.driver.rm_cert()

    def assertPamReturns(self, user, service, rc,
                         host=None, pam_mod_opts=None,
                         additional_modules=None):
        if host is None:
            host = self.client_hostname
        self._config_setup(host)

        svc_file = self._write_pam_svc_file(service,
                                            self.ph_abspath,
                                            self.config_file.name,
                                            pam_mod_opts,
                                            additional_modules)
        try:
            tc = pypamtest.TestCase(pypamtest.PAMTEST_ACCOUNT, rc)
            self._run_pwrap_test(tc, user, service)
        finally:
            os.unlink(svc_file.name)

    def assertPamReturnsForHost(self, user, service, rc, host=None):
        if host is not None:
            os.environ["HOST_NAME"] = host
        try:
            self.assertPamReturns(user, service, rc, host)
        finally:
            os.environ["HOST_NAME"] = self.client_hostname

    def assertAllowed(self, user, service, host=None):
        self.assertPamReturnsForHost(user, service, 0, host)

    def assertDenied(self, user, service, host=None):
        self.assertPamReturnsForHost(user, service, 6, host)

    def _run_pwrap_test(self, tc, user, service):
        res = pypamtest.run_pamtest(user, service, [tc])

    def _driver_setup(self):
        ipa_hostname = os.getenv("IPA_HOSTNAME")
        if ipa_hostname is None:
            raise ValueError("IPA server hostname to test against not set!\n")

        ipa_domain = os.getenv("IPA_DOMAIN")
        if ipa_domain is None:
            raise ValueError("IPA server domain to test against not set!\n")

        admin_password = os.getenv("ADMIN_PASSWORD")
        if admin_password is None:
            raise ValueError("IPA admin password is not set!\n")

        insecure = os.getenv("INSECURE_TESTS")
        if insecure is not None:
            insecure = True

        bind_dn = os.getenv("BIND_DN")
        if bind_dn is None:
            raise ValueError("The bind user is not set\n")

        bind_pw = os.getenv("BIND_PW")
        if bind_pw is None:
            raise ValueError("The bind password is not set\n")

        self.driver = IpaClientlessTestDriver(ipa_hostname,
                                              ipa_domain,
                                              admin_password,
                                              bind_dn,
                                              bind_pw,
                                              insecure=True)

    def _pwrap_setup(self):
        if os.getenv("PAM_WRAPPER") is None:
            raise ValueError("PAM_WRAPPER is not initialized\n")

        self.pwrap_runtimedir = os.getenv("PAM_WRAPPER_RUNTIME_DIR")
        if self.pwrap_runtimedir is None:
            raise ValueError("The PAM_WRAPPER_RUNTIME_DIR variable is unset\n")

        if not os.access(self.pwrap_runtimedir, os.O_RDWR):
            raise IOError("Cannot access %s\n", self.pwrap_runtimedir)

        self.ph_abspath = os.getenv("PAM_HBAC_ABS_PATH")
        if self.ph_abspath is None:
            raise ValueError("The pam_hbac absolute path is unset\n")

    def _config_write(self, config_path, confd):
        f = open(config_path, 'w')
        for key in confd:
            f.write("%s=%s\n" % (key, confd[key]))
        f.flush()
        return f

    def _config_setup(self, host):
        self.config_file = None

        config_path = os.getenv("PAM_HBAC_CONFIG_PATH")
        if config_path is None:
            return

        base_dn = os.getenv("IPA_BASEDN")
        if base_dn is None:
            raise ValueError("IPA server basedn to test against is not set!\n")

        confd = {}
        confd['URI'] = "ldap://" + self.driver.hostname
        confd['BASE'] = base_dn
        confd['BIND_DN'] = self.driver.bind_dn
        confd['BIND_PW'] = self.driver.bind_pw
        confd['CA_CERT'] = self.driver.ca_cert
        confd['HOST_NAME'] = host

        self.config_file = self._config_write(config_path, confd)

    def _write_pam_svc_file(self, svc_name, module_abspath,
                            config_file=None, pam_mod_opts=None,
                            additional_modules=None):
        svcfile = os.path.join(self.pwrap_runtimedir, svc_name)
        f = open(svcfile, 'w')
        content = self._gen_pam_svc_file(module_abspath,
                                         config_file,
                                         pam_mod_opts,
                                         additional_modules)
        f.write(content)
        f.flush()
        return f

    def _gen_pam_svc_file(self, module_abspath,
                          config_file=None,
                          pam_mod_opts=None,
                          additional_modules=None):
        content = "account required %s" % module_abspath
        if config_file is not None:
            content = content + " config=%s" % config_file
        if pam_mod_opts is not None:
            content = content + " " + " ".join([opt for opt in pam_mod_opts])
        content = content + "\n"
        if additional_modules is not None:
            for mod_kv in additional_modules:
                for module, action in mod_kv.items():
                    content = content + "account %s %s\n" % (action, module)
        return content

    def create_direct_entries(self, direct_user_name,
                              service_name,
                              rule_host, non_rule_host):
        self.tuser = IpaClientlessPamHbacUser(self.driver, direct_user_name)
        self.tuser.add()

        self.client = IpaClientlessPamHbacHost(self.driver, rule_host)
        self.client.add()
        self.nonrule_client = IpaClientlessPamHbacHost(self.driver,
                                                       non_rule_host)
        self.nonrule_client.add()

        self.rule_svc = IpaClientlessPamHbacService(self.driver, service_name)
        self.rule_svc.add()

    def remove_direct_entries(self):
        self.tuser.remove()
        self.client.remove()
        self.nonrule_client.remove()
        self.trule.remove()
        self.rule_svc.remove()


class PamHbacTestAllowAll(PamHbacTestCase):
    def setUp(self):
        super(PamHbacTestAllowAll, self).setUp()
        self.allow_all = IpaClientlessPamHbacRule(self.driver, "allow_all")

    def tearDown(self):
        super(PamHbacTestAllowAll, self).tearDown()

    def test_allow_all(self):
        self.allow_all.enable()
        self.allow_all.add_all_cats()
        self.assertAllowed("admin", "sshd")

    def test_allow_all_disabled(self):
        self.allow_all.disable()
        self.assertDenied("admin", "sshd")
        self.allow_all.enable()


class PamHbacTestDirect(PamHbacTestCase):
    def setUp(self):
        super(PamHbacTestDirect, self).setUp()
        self.allow_all = IpaClientlessPamHbacRule(self.driver, "allow_all")
        self.allow_all.disable()
        self.create_direct_entries("tuser", "rulesvc", "rulehost", "nonrulehost")

        self.trule = IpaClientlessPamHbacRule(self.driver, "trule")
        self.trule.add()
        # it would be better to pass the objects, not just strings maybe?
        self.trule.add_svc(self.rule_svc.name)
        self.trule.add_user(self.tuser.name)
        self.trule.add_host(self.client.name)

    def tearDown(self):
        self.allow_all.enable()
        self.remove_direct_entries()
        super(PamHbacTestDirect, self).tearDown()

    def test_allow_rule_user(self):
        """
        The user who is assigned to the rule should be allowed to log in the
        host referenced in the rule using the service referenced in the rule
        """
        self.assertAllowed(self.tuser.name, self.rule_svc.name, self.client.name)
        # Sanity-check: Access must be denied if the rule is disabled
        self.trule.disable()
        self.assertDenied(self.tuser.name, self.rule_svc.name, self.client.name)
        self.trule.enable()

    def test_deny_non_rule_user(self):
        """
        A different user who is assigned to the rule should not be allowed to
        log in the host referenced in the rule using the service referenced
        in the rule
        """
        self.assertAllowed("admin", self.rule_svc.name, self.client.name)

    def test_deny_non_rule_svc(self):
        """
        The user who is assigned to the rule should not be allowed to log in
        the host referenced in the rule using a different service than
        the one referenced in the rule
        """
        self.assertDenied(self.tuser.name, "login", self.client.name)

    def test_deny_non_rule_host(self):
        """
        The user who is assigned to the rule should not be allowed to log
        in to another host than the one referenced in the rule using the
        service referenced in the rule
        """
        self.assertDenied(self.tuser.name,
                          self.rule_svc.name,
                          self.nonrule_client.name)


class PamHbacTestGroup(PamHbacTestCase):
    def setUp(self):
        super(PamHbacTestGroup, self).setUp()
        self.allow_all = IpaClientlessPamHbacRule(self.driver, "allow_all")
        self.allow_all.disable()

        self.create_direct_entries("tuser", "rulesvc", "rulehost", "nonrulehost")

        self.tgroup = IpaClientlessPamHbacUserGroup(self.driver, "tgroup")
        self.tgroup.add()
        self.tgroup.add_member(self.tuser.name)

        self.rule_hg = IpaClientlessPamHbacHostGroup(self.driver,
                                                     "rulehostgroup")
        self.rule_hg.add()
        self.rule_hg.add_member(self.client.name)

        self.non_rule_hg = IpaClientlessPamHbacHostGroup(self.driver,
                                                         "nonrulehostgroup")
        self.non_rule_hg.add()
        self.non_rule_hg.add_member(self.nonrule_client.name)

        self.rule_svc_group = IpaClientlessPamHbacServiceGroup(self.driver,
                                                               "ruleservicegroup")
        self.rule_svc_group.add()
        self.rule_svc_group.add_member(self.rule_svc.name)

        self.trule = IpaClientlessPamHbacRule(self.driver, "group_rule")
        self.trule.add()
        self.trule.add_svc(svcgroup=self.rule_svc_group.name)
        self.trule.add_user(usergroup=self.tgroup.name)
        self.trule.add_host(hostgroup=self.rule_hg.name)

    def tearDown(self):
        self.allow_all.enable()
        self.remove_direct_entries()
        self.tgroup.remove()
        self.rule_hg.remove()
        self.non_rule_hg.remove()
        self.rule_svc_group.remove()
        super(PamHbacTestGroup, self).tearDown()

    def test_allow_rule_group_user(self):
        """
        The user who is a member of a group assigned to the rule should
        be allowed to log in the host that is a member of the hostgroup
        referenced in the rule using a service that is a member of a
        service group referenced in the rule
        """
        self.assertAllowed(self.tuser.name, self.rule_svc.name, self.client.name)
        # Sanity-check: Access must be denied if the rule is disabled
        self.trule.disable()
        self.assertDenied(self.tuser.name, self.rule_svc.name, self.client.name)
        self.trule.enable()

    def test_deny_non_rule_group_user(self):
        """
        A user who is a not member of a group assigned to the rule should
        not be allowed to log in the host that is a member of the hostgroup
        referenced in the rule using a service that is a member of a
        service group referenced in the rule
        """
        self.assertDenied("admin", self.rule_svc.name, self.client.name)

    def test_deny_non_rule_svc(self):
        """
        The user who is assigned to the rule should not be allowed to log in
        the host referenced in the rule using a different service than
        the one referenced in the rule via svcgroup
        """
        self.assertDenied(self.tuser.name, "login", self.client.name)

    def test_deny_non_rule_host(self):
        """
        The user who is assigned to the rule should not be allowed to log
        in to another host than the one referenced in the rule using the
        service referenced in the rule
        """
        self.assertDenied(self.tuser.name,
                          self.rule_svc.name,
                          self.nonrule_client.name)


class PamHbacTestErrorConditions(PamHbacTestCase):
    def setUp(self):
        super(PamHbacTestErrorConditions, self).setUp()

    def tearDown(self):
        super(PamHbacTestErrorConditions, self).tearDown()

    def test_no_such_user(self):
        """"
        Unknown user should return 10 = User not known to the underlying
        module, at least on Linux
        """
        self.assertPamReturns("no_such_user", "sshd", 10)

    def test_ignore_unknown_user(self):
        """"
        Unknown user should return 25 = Ignore underlying account
        module, at least on Linux. By adding pam_permit, this test will
        return PAM_SUCCESS as a whole, otherwise it would return permission
        denied.
        """
        self.assertPamReturns("no_such_user_ignore", "sshd", 0,
                              pam_mod_opts=["ignore_unknown_user"],
                              additional_modules=[ { "pam_permit.so":"required"}])

    def test_root(self):
        """
        Root is a special case and should be tested separately
        """
        self.assertPamReturns("root", "sshd", 10)
        self.assertPamReturns("root", "sshd", 0,
                              pam_mod_opts=["ignore_unknown_user"],
                              additional_modules=[ { "pam_permit.so":"required"}])


    def test_no_such_service(self):
        """"
        Unknown user should return 10 = User not known to the underlying
        module, at least on Linux. But since there is no other
        """
        self.assertPamReturns("admin", "no_such_service", 6)

    def test_no_such_host(self):
        """"
        Unknown host should just deny access
        """
        self.assertDenied("admin", "sshd", "no_such_host")


if __name__ == "__main__":
    unittest.main()
