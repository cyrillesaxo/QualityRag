"""Local Semantic workbench HTTP security + end-to-end browser bridge tests."""
import http.client
import json
import sqlite3
import tempfile
import threading
from pathlib import Path
import sys
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_workbench import create_app

TOKEN="local-test-token-longer-than-24-characters"


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/"team.csv").write_text("name,role\nCyrille,architect\n",encoding="utf8")
        handler,self.db=create_app(self.root,self.root/"workbench.sqlite3",TOKEN,namespace="local")
        self.server=ThreadingHTTPServer(("127.0.0.1",0),handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.db.close()
        self.temp.cleanup()

    def call(self,path,body=None,token=TOKEN,origin=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        headers={"Authorization":"Bearer "+token}
        if origin:
            headers["Origin"]=origin
        if body is not None:
            headers["Content-Type"]="application/json"
            data=json.dumps(body)
            headers["Content-Length"]=str(len(data))
            method="POST"
        else:
            data=None
            method="GET"
        conn.request(method,path,body=data,headers=headers)
        response=conn.getresponse()
        out=response.read().decode("utf8")
        result=response.status,json.loads(out)
        conn.close()
        return result

    def test_local_query_flow(self):
        status,data=self.call("/semantic/status")
        self.assertEqual(status,200)
        self.assertEqual(data["namespace"],"local")
        status,data=self.call("/semantic/index",{})
        self.assertEqual(status,200)
        self.assertEqual(data["coverage"]["indexed"],1)
        status,data=self.call("/semantic/find",{"statement":"FIND 'Cyrille' IN 'local' LIMIT 10;"})
        self.assertEqual(status,200)
        self.assertEqual(len(data["result"]["hits"]),1)
        self.assertEqual(data["result"]["hits"][0]["anchor"]["row_number"],2)
        self.assertEqual(data["admission"],"INCONCLUSIVE")

    def test_registry_token_cannot_authenticate(self):
        self.assertEqual(self.call("/semantic/status",token="wrong")[0],401)
        self.assertEqual(self.call("/semantic/index",{},token="wrong")[0],401)

    def test_external_origin_is_rejected(self):
        self.assertEqual(self.call("/semantic/index",{},origin="https://attacker.invalid")[0],403)

    def test_user_cannot_override_directory_path_or_namespace(self):
        self.assertEqual(self.call("/semantic/index",{"directory":"/etc"})[0],400)
        self.assertEqual(self.call("/semantic/find",{"statement":"FIND 'Cyrille' IN 'other' LIMIT 10;"})[0],400)
        self.assertEqual(self.call("/semantic/find",{"statement":"DELETE FROM facts"})[0],400)

    def test_auth_required_to_read_status(self):
        self.assertEqual(self.call("/semantic/status",token="")[0],401)


if __name__=="__main__":
    unittest.main()
