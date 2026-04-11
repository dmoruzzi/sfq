"""
Bulk API v2 client module for the SFQ library.

This module provides Bulk API v2 operations for processing large
datasets asynchronously in Salesforce.
"""

import json
import time
from typing import Any, Dict, Iterable, List, Optional

from .utils import get_logger

logger = get_logger("sfq.bulk_v2")


class BulkAPIV2Client:
    """
    Client for Bulk API v2 operations on Salesforce records.

    This class handles bulk delete operations using the Bulk API v2,
    which is optimized for processing large datasets asynchronously.
    """

    def __init__(
        self,
        http_client: "HTTPClient",  # Forward reference to avoid circular import  # noqa: F821
        api_version: str = "v65.0",
    ) -> None:
        """
        Initialize the Bulk API v2 client.

        :param http_client: HTTPClient instance for making HTTP requests
        :param api_version: Salesforce API version to use
        """
        self.http_client = http_client
        self.api_version = api_version

    def delete(
        self,
        sobject: str,
        ids: Iterable[str],
        batch_size: int = 10000,
        poll_interval_seconds: float = 5.0,
        max_poll_seconds: float = 300.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Delete multiple records using the Bulk API v2 delete job.

        This method creates a bulk delete job, uploads the IDs, and waits
        for the job to complete.

        :param sobject: The sObject API name (e.g., 'Account', 'Nebula__Log__c')
        :param ids: An iterable of record IDs to delete
        :param batch_size: Number of IDs to process in a single bulk job (default 10000)
        :param poll_interval_seconds: Seconds between status polls
        :param max_poll_seconds: Maximum time to wait for job completion
        :return: Dict with job results or None on failure
        """
        id_list = list(ids)
        if not id_list:
            logger.warning("No IDs provided for bulk delete")
            return None

        logger.debug(
            "Starting bulk delete for %s %s records", len(id_list), sobject
        )

        # Split into batches if needed
        batches = [id_list[i:i + batch_size] for i in range(0, len(id_list), batch_size)]
        
        all_results = []
        
        for batch_idx, batch_ids in enumerate(batches):
            logger.debug("Processing batch %d/%d", batch_idx + 1, len(batches))
            
            # Create the delete job
            job_id = self._create_delete_job(sobject)
            if not job_id:
                logger.error("Failed to create delete job for batch %d", batch_idx + 1)
                all_results.append({"error": "Failed to create job", "batch": batch_idx})
                continue
            
            # Upload the IDs
            if not self._upload_delete_data(job_id, batch_ids):
                logger.error("Failed to upload delete data for job %s", job_id)
                self._abort_job(job_id)
                all_results.append({"error": "Failed to upload data", "job_id": job_id, "batch": batch_idx})
                continue
            
            # Close the job to start processing
            if not self._close_job(job_id):
                logger.error("Failed to close job %s", job_id)
                all_results.append({"error": "Failed to close job", "job_id": job_id, "batch": batch_idx})
                continue
            
            # Poll for completion
            result = self._poll_job(
                job_id,
                poll_interval_seconds=poll_interval_seconds,
                max_poll_seconds=max_poll_seconds,
            )
            
            if result:
                all_results.append(result)
                logger.debug("Batch %d completed: %s", batch_idx + 1, result.get("state"))
            else:
                logger.error("Job %s failed to complete", job_id)
                all_results.append({"error": "Job failed to complete", "job_id": job_id, "batch": batch_idx})

        return {
            "batches": len(batches),
            "results": all_results,
        }

    def _create_delete_job(self, sobject: str) -> Optional[str]:
        """
        Create a Bulk API v2 delete job.

        :param sobject: The sObject API name
        :return: Job ID or None on failure
        """
        endpoint = f"/services/data/{self.api_version}/jobs/ingest"

        payload = {
            "operation": "delete",
            "object": sobject,
            "contentType": "CSV",
            "lineEnding": "LF",
        }

        try:
            status_code, data = self.http_client.send_authenticated_request(
                method="POST",
                endpoint=endpoint,
                body=json.dumps(payload),
            )

            if status_code in [200, 201]:
                logger.debug("Created delete job for %s", sobject)
                result = json.loads(data)
                return result.get("id")

            logger.error("Failed to create delete job: %s", status_code)
            logger.debug("Response body: %s", data)

        except Exception as e:
            logger.exception("Exception creating delete job: %s", e)

        return None

    def _upload_delete_data(self, job_id: str, ids: List[str]) -> bool:
        """
        Upload IDs to a delete job.

        :param job_id: The job ID
        :param ids: List of record IDs to delete
        :return: True on success
        """
        endpoint = f"/services/data/{self.api_version}/jobs/ingest/{job_id}/batches"

        # Create CSV content with Id column
        csv_content = "Id\n" + "\n".join(ids) + "\n"

        try:
            headers = self.http_client.get_common_headers()
            headers["Content-Type"] = "text/csv"

            status_code, data = self.http_client.send_request(
                method="PUT",
                endpoint=endpoint,
                headers=headers,
                body=csv_content,
            )

            if status_code in [200, 201, 204]:
                logger.debug("Uploaded %d IDs to job %s", len(ids), job_id)
                return True

            logger.error("Failed to upload data: %s", status_code)
            logger.debug("Response: %s", data)

        except Exception as e:
            logger.exception("Exception uploading data: %s", e)

        return False

    def _close_job(self, job_id: str) -> bool:
        """
        Close a job to start processing.

        :param job_id: The job ID
        :return: True on success
        """
        endpoint = f"/services/data/{self.api_version}/jobs/ingest/{job_id}"

        payload = {"state": "UploadComplete"}

        try:
            status_code, data = self.http_client.send_authenticated_request(
                method="PATCH",
                endpoint=endpoint,
                body=json.dumps(payload),
            )

            if status_code in [200, 201]:
                logger.debug("Closed job %s", job_id)
                return True

            logger.error("Failed to close job: %s", status_code)
            logger.debug("Response: %s", data)

        except Exception as e:
            logger.exception("Exception closing job: %s", e)

        return False

    def _abort_job(self, job_id: str) -> bool:
        """
        Abort a job.

        :param job_id: The job ID
        :return: True on success
        """
        endpoint = f"/services/data/{self.api_version}/jobs/ingest/{job_id}"

        payload = {"state": "Aborted"}

        try:
            status_code, data = self.http_client.send_authenticated_request(
                method="PATCH",
                endpoint=endpoint,
                body=json.dumps(payload),
            )

            if status_code in [200, 201]:
                logger.debug("Aborted job %s", job_id)
                return True

            logger.error("Failed to abort job: %s", status_code)

        except Exception as e:
            logger.exception("Exception aborting job: %s", e)

        return False

    def _poll_job(
        self,
        job_id: str,
        poll_interval_seconds: float = 5.0,
        max_poll_seconds: float = 300.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Poll for job completion.

        :param job_id: The job ID
        :param poll_interval_seconds: Seconds between polls
        :param max_poll_seconds: Maximum time to wait
        :return: Job result dict or None on failure
        """
        endpoint = f"/services/data/{self.api_version}/jobs/ingest/{job_id}"
        
        start_time = time.time()
        
        while True:
            try:
                status_code, data = self.http_client.send_authenticated_request(
                    method="GET",
                    endpoint=endpoint,
                )

                if status_code == 200:
                    result = json.loads(data)
                    state = result.get("state")
                    
                    logger.debug("Job %s state: %s", job_id, state)
                    
                    if state == "JobComplete":
                        return result
                    elif state == "Failed":
                        logger.error("Job %s failed: %s", job_id, result)
                        return result
                    elif state == "Aborted":
                        logger.warning("Job %s was aborted", job_id)
                        return result
                    elif state == "InProgress" or state == "UploadComplete":
                        logger.debug("Job %s still processing (state: %s)", job_id, state)
                
                logger.debug("Job status request returned: %s (state not terminal)", status_code)

            except Exception as e:
                logger.exception("Exception polling job: %s", e)
                return None
            
            elapsed = time.time() - start_time
            if elapsed >= max_poll_seconds:
                logger.error("Job %s timed out after %s seconds", job_id, elapsed)
                return None
            
            time.sleep(poll_interval_seconds)

    def _get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a job.

        :param job_id: The job ID
        :return: Job status dict or None on failure
        """
        endpoint = f"/services/data/{self.api_version}/jobs/ingest/{job_id}"

        try:
            status_code, data = self.http_client.send_authenticated_request(
                method="GET",
                endpoint=endpoint,
            )

            if status_code == 200:
                return json.loads(data)

            logger.error("Failed to get job status: %s", status_code)

        except Exception as e:
            logger.exception("Exception getting job status: %s", e)

        return None