from itertools import chain
import re

from . import APIClient, Project


class RedmineClient(APIClient):
    PAGE_MAX_SIZE = 100

    def get_auth_headers(self):
        return {"X-Redmine-API-Key": self.api_key}

    def get(self, *args, **kwargs):
        # In detail views, redmine encapsulate "foo" typed objects under a
        # "foo" key on the JSON.
        ret = super().get(*args, **kwargs)
        values = ret.values()
        if len(values) == 1:
            return list(values)[0]
        else:
            return ret

    def unpaginated_get(self, *args, **kwargs):
        """ Iterates over API pagination for a given resource list
        """
        resp = self.get(*args, **kwargs)

        # Try to autofind the top-level key containing
        keys_candidates = (
            set(resp.keys()) - set(['total_count', 'offset', 'limit']))

        assert len(keys_candidates) == 1
        res_list_key = list(keys_candidates)[0]

        kwargs['params'] = kwargs.get('params', {})
        kwargs['params']['limit'] = self.PAGE_MAX_SIZE

        result_pages = [resp[res_list_key]]
        while (resp['total_count'] - resp['offset'] - resp['limit']) > 0:
            kwargs['offset'] = kwargs.get('offset', 0) + self.PAGE_MAX_SIZE
            resp = self.get(*args, **kwargs)
            result_pages.append(resp[res_list_key])

        return chain.from_iterable(result_pages)


class RedmineProject(Project):
    REGEX_PROJECT_URL = re.compile(
        r'^(?P<base_url>https?://.*)/projects.*/(?P<project_name>[\w_-]+)$')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_url = '{}.json'.format(self.public_url)
        self.instance_url = self._url_match.group('base_url')

    def get_all_issues(self):
        issues = self.api.unpaginated_get(
            '{}/issues.json?status_id=*'.format(self.public_url))
        detailed_issues = []
        # It's impossible to get issue history from list view, so get it from
        # detail view...

        for issue_id in (i['id'] for i in issues):
            issue_url = '{}/issues/{}.json?include=journals,watchers,relations,childrens,attachments'.format(
                self.instance_url, issue_id)
            detailed_issues.append(self.api.get(issue_url))

        return detailed_issues

    def get_participants(self):
        """Get participating users (issues authors/owners)

        :return: list of all users participating on issues
        :rtype: list
        """
        user_ids = set()
        users = []
        # FIXME: cache
        for i in self.get_all_issues():
            for i in chain(i.get('watchers', []),
                           [i['author'], i.get('assigned_to', None)]):

                if i is None:
                    continue
                user_ids.add(i['id'])

        for i in user_ids:
            users.append(self.api.get('{}/users/{}.json'.format(
                self.instance_url, i)))
        return users

    def get_users_index(self):
        """ Returns dict index of users (by user id)
        """
        return {i['id']: i for i in self.get_participants()}

    def get_versions(self):
        response = self.api.get('{}/versions.json'.format(self.public_url))
        return response['versions']
