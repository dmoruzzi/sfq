import difflib
import http.client
import json

from sfq import SFAuth

from prompt_toolkit import prompt
from prompt_toolkit.completion import Completer, Completion

def _interactive_shell(sf: SFAuth, dry_run: bool, disable_fuzzy_completion: bool):
    """Runs an interactive REPL for querying Salesforce data with real-time autocompletion."""

    sobject = None
    fields = None

    class DynamicSeparatorCompleter(Completer):
        """Custom completer that adapts to different separators."""
        
        def __init__(self, words: list[str], separators: list[str] = [","]):
            self.words = words
            self.separators = separators

        def get_completions(self, document, complete_event):
            text_before_cursor = document.text_before_cursor
            
            for separator in self.separators:
                if separator in text_before_cursor:
                    last_token = text_before_cursor.split(separator)[-1].strip()
                    break
            else:
                last_token = text_before_cursor.strip()


            matches_difflib = difflib.get_close_matches(last_token, self.words, n=20, cutoff=0.6)
            matches_starting = [word for word in self.words if word.lower().startswith(last_token.lower())]

            if not disable_fuzzy_completion and (len(last_token) > 6 or not(matches_starting)):
                matches = matches_difflib
            else:
                matches = matches_starting

            for word in matches:
                yield Completion(word, start_position=-len(last_token))
                
    def _get_objects(sf: SFAuth):
        """Retrieve available Salesforce objects."""
        host = sf.instance_url.split("://")[1].split("/")[0]
        conn = http.client.HTTPSConnection(host)
        uri = f"/services/data/{sf.api_version}/sobjects/"
        token = sf._refresh_token_if_needed()
        headers = {'Authorization': f'Bearer {token}'}
        print(f'token: {token}')
        conn.request("GET", uri, headers=headers)
        response = conn.getresponse()
        
        if response.status != 200:
            print(f'Error: {response.status} {response.reason}')
            return []
        
        data = json.loads(response.read())
        return [sobject['name'] for sobject in data['sobjects']]

    def _get_fields(sobject: str, sf: SFAuth):
        """Retrieve available fields for a given Salesforce object."""
        host = sf.instance_url.split("://")[1].split("/")[0]
        conn = http.client.HTTPSConnection(host)
        uri = f"/services/data/{sf.api_version}/sobjects/{sobject}/describe/"
        headers = {'Authorization': f'Bearer {sf._refresh_token_if_needed()}'}
        conn.request("GET", uri, headers=headers)
        response = conn.getresponse()
        
        if response.status != 200:
            print(f'Error: {response.status} {response.reason}')
            raise ValueError(f'Unable to fetch fields for sObject "{sobject}": {response.status}, {response.reason}')
        
        data = json.loads(response.read())
        return [f['name'] for f in data['fields']]

    available_objects = _get_objects(sf)
    
    object_completer = DynamicSeparatorCompleter(available_objects)
    while not sobject:
        sobject = prompt('FROM ', completer=object_completer).strip()


    available_fields = _get_fields(sobject, sf)
    field_completer = DynamicSeparatorCompleter(available_fields, separators=[","])
    while not fields:
        fields = prompt('SELECT ', completer=field_completer).strip()

    where_completer = DynamicSeparatorCompleter(available_fields, separators=[" AND ", " OR "])
    where = prompt("WHERE ", completer=where_completer).strip()
    where_clause = f"WHERE {where}" if where else ""
    
    limit = prompt("LIMIT ", default="200").strip()
    limit_clause = f"LIMIT {limit}" if limit else ""
    
    query = f"SELECT {fields} FROM {sobject} {where_clause} {limit_clause}".replace('  ', ' ')
    
    if dry_run:
        print('\nDry-run, skipping execution...')
        print(f'\nQuery: {query}\n')
        return query
    
    print('\nExecuting query...\n')
    data = sf.query(query)
    print(json.dumps(data, indent=4))
    print(f'\nQuery: {query}\n')
    return data

if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description='Interactively query Salesforce data with real-time autocompletion.'
    )
    parser.add_argument(
        '-a', '--sfdxAuthUrl', type=str, help='Salesforce auth url', default=os.environ.get('SFDX_AUTH_URL')
    )
    parser.add_argument(
        '--dry-run', action='store_true', help='Print the query without executing it', default=str(os.environ.get('SFQ_DRY_RUN')),
    )
    parser.add_argument(
        '--disable-fuzzy-completion', action='store_true', help='Disable fuzzy completion', default=str(os.environ.get('SFQ_DISABLE_FUZZY_COMPLETION')),
    )
    args = parser.parse_args()

    if not args.sfdxAuthUrl:
        raise ValueError('SFDX_AUTH_URL environment variable is not set nor provided as an argument')
    
    try:
        if args.dry_run.lower() not in ['true', '1']:
            args.dry_run = False
    except AttributeError:
        pass

    try:
        if args.disable_fuzzy_completion.lower() not in ['true', '1']:
            args.disable_fuzzy_completion = False
    except AttributeError:
        pass


    _interactive_shell(
        SFAuth(
            instance_url=f"https://{str(args.sfdxAuthUrl).split('@')[1]}",
            client_id=str(args.sfdxAuthUrl).split('//')[1].split('::')[0],
            refresh_token=str(args.sfdxAuthUrl).split('::')[1].split('@')[0],
        ),
        args.dry_run,
        args.disable_fuzzy_completion
    )
