package gov.epa.rcra.rest.manifest;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;

@Service
public class ManifestService {

    private final ManifestClient manifestClient;

    ManifestService(ManifestClient manifestClient) {
        this.manifestClient = manifestClient;
    }

    public String getEmanifest(String manifestTrackingNumber) throws ManifestException {
        return manifestClient.getEmanifest(manifestTrackingNumber);
    }

    public String createPaperManifest(MultipartFile file, String data) throws ManifestException {
        byte[] fileBytes;
        try {
            fileBytes = file.getBytes();
        } catch (IOException e) {
            throw new ManifestException(HttpStatus.INTERNAL_SERVER_ERROR.value());
        }
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("attachment", fileBytes);
        body.add("manifest", data);

        return manifestClient.createPaperManifest(body);
    }
}
