Data holders can grant access to pull software artifacts once they register in the platform through the specific section in the Dashboard (see section 6). Only Software developers can push SW artifacts in the repository, which have to be validated by the technical committee. Software developers register through the form indicated at the beginning of this section.


Figure 5.5. View of the user profile option (left) and the information on the user profile (right) in the SW registry of EUCAIM.
Two subrepositories (projects in the harbor jargon) are available:

ingestion-tools, for tools developed to prepare or upload the data by the data holders. These tools would be downloadable and could be used by the Data Holders in their own premises, once they have access granted.

processing-tools, for tools developed to process the data. The tools in processing-tool project will be mainly used in the processing environment. Tools cannot be downloaded outside of the Processing environment boundaries.

The procedure for pulling or pushing an OCI-compliant artifact (e.g. a Docker container) is the following:

Retrieve the user and access token through the harbor registry user profile (see figure 5.1)

Open a terminal on a computer with Docker installed (version 25 or higher).

Login through docker login harbor.eucaim.cancerimage.eu -u <<user>> -p <<token>>, replacing <> and <> by the values obtained in the user's profile.

Push an image using the standard Docker command: docker push harbor.eucaim.cancerimage.eu/<<project>>/<<image_name>>:<<tag>>, replacing <<project>> by one of the two projects available: ingestion-tools if the tool is related to data preparation and uploading or eucaim in case of a processing tool. Replace <<image_name>> and <<tag>> by the appropriate values.

Pull an image using the Docker command: docker pull harbor.eucaim.cancerimage.eu/<<project>>/<<image_name>>:<<tag>>. Replace the values into curly brackets by the appropriate values.