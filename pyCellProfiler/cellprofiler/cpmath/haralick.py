"""Haralick texture features."""

import numpy as np
import scipy.ndimage as scind
from scipy.linalg.basic import toeplitz

def minimum(input, labels, index):
    r = scind.minimum(input, labels, index)
    if len(index) == 1:
        r = [r]
    return np.array(r)

def maximum(input, labels, index):
    r = scind.maximum(input, labels, index)
    if len(index) == 1:
        r = [r]
    return np.array(r)

def normalized_per_object(image, labels):
    """Normalize the intensities of each object to the [0, 1] range."""
    nobjects = labels.max()
    objects = np.arange(nobjects + 1)
    lmax = maximum(image, labels, objects)
    lmin = minimum(image, labels, objects)
    # Divisor is the object's max - min, or 1 if they are the same.
    divisor = np.ones((nobjects + 1,))
    divisor[lmax > lmin] = (lmax - lmin)[lmax > lmin]
    return (image - lmin[labels]) / divisor[labels]

def quantize(image, nlevels):
    """Quantize an image into integers 0, 1, ..., nlevels - 1.

    image   -- a numpy array of type float, range [0, 1]
    nlevels -- an integer
    """
    tmp = np.array(image // (1.0 / nlevels), dtype='i1')
    return tmp.clip(0, nlevels - 1)

def cooccurrence(quantized_image, labels, scale=3):
    """Calculates co-occurrence matrices for all the objects in the image.

    Return an array P of shape (nobjects, nlevels, nlevels) such that
    P[o, :, :] is the cooccurence matrix for object o.

    quantized_image -- a numpy array of integer type
    labels          -- a numpy array of integer type
    scale           -- an integer

    For each object O, the cooccurrence matrix is defined as follows.
    Given a row number I in the matrix, let A be the set of pixels in
    O with gray level I, excluding pixels in the rightmost S
    columns of the image.  Let B be the set of pixels in O that are S
    pixels to the right of a pixel in A.  Row I of the cooccurence
    matrix is the gray-level histogram of the pixels in B.
    """
    nlevels = quantized_image.max() + 1
    nobjects = labels.max()
    image_a = quantized_image[:, :-scale]
    image_b = quantized_image[:, scale:]
    labels_ab = labels[:, :-scale]
    equilabel = labels[:, :-scale] == labels[:, scale:]
    P, bins_P = np.histogramdd([labels_ab[equilabel], image_a[equilabel],
                                image_b[equilabel]],
                               (nobjects, nlevels, nlevels))
    return np.array(P, dtype='int32')

class Haralick(object):
    """
    Calculate the Haralick texture features.

    Currently, the implementation uses nevels = 8 different grey
    levels.

    The original reference is: Haralick et al. (1973), Textural
    Features for Image Classification, _IEEE Transaction on Systems
    Man, Cybernetics_, SMC-3(6):610-621.  BEWARE: There are lots of
    erroneous formulas for the Haralick features in the
    literature.  There is also an error in the original paper.
    """
    def __init__(self, image, labels, scale, nlevels=8):
        """
        image   -- 2-D numpy array of 32-bit floating-point numbers.
        labels  -- 2-D numpy array of integers.
        scale   -- an integer.
        nlevels -- an integer
        """
        normalized = normalized_per_object(image, labels)
        quantized = quantize(normalized, nlevels)
        self.P = cooccurrence(quantized, labels, scale)
        self.P = np.array(self.P, dtype=float) / self.P.sum()

        self.nobjects = labels.max()
        px = self.P.sum(2) # nobjects x nlevels
        py = self.P.sum(1) # nobjects x nlevels
        self.levels = np.arange(nlevels)
        self.rlevels = np.tile(self.levels, (self.nobjects, 1))
        self.levels2 = np.arange(2 * nlevels - 1)
        self.rlevels2 = np.tile(self.levels2, (self.nobjects, 1))
        self.mux = ((self.rlevels + 1) * px).sum(1)
        self.muy = ((self.rlevels + 1) * py).sum(1)
        self.sigmax = np.sqrt(((self.rlevels + 1 - self.mux) ** 2 * px).sum(1))
        self.sigmay = np.sqrt(((self.rlevels + 1 - self.muy) ** 2 * py).sum(1))
        eps = np.finfo(float).eps
        self.hx = -(px * np.log(px + eps)).sum(1)
        self.hy = -(py * np.log(py + eps)).sum(1)
        pxpy = np.array([np.dot(px[i,:,np.newaxis], py[i,np.newaxis])
                         for i in range(self.nobjects)])
        self.hxy1 = -(self.P * np.log(pxpy + eps)).sum(2).sum(1)
        self.hxy2 = -(pxpy * np.log(pxpy + eps)).sum(2).sum(1)
        self.eps = eps

        self.p_xplusy = np.zeros((self.nobjects, 2 * nlevels - 1))
        self.p_xminusy = np.zeros((self.nobjects, nlevels))
        for x in self.levels:
            for y in self.levels:
                self.p_xplusy[:, x + y] += self.P[:, x, y]
                self.p_xminusy[:, np.abs(x - y)] += self.P[:, x, y]

    # The remaining methods are for computing all the Haralick
    # features.  Each methods returns a vector of length nobjects.

    def H1(self):
        "Angular second moment."
        return(self.P ** 2).sum(2).sum(1)

    def H2(self):
        "Contrast."
        return (self.rlevels ** 2 * self.p_xminusy).sum(1)

    def H3(self):
        "Correlation."
        multiplied = np.dot(self.levels[:, np.newaxis] + 1,
                            self.levels[np.newaxis] + 1)
        repeated = np.tile(multiplied[np.newaxis], (self.nobjects, 1, 1))
        summed = (repeated * self.P).sum(2).sum(1)
        h3 = (summed - self.mux * self.muy) / (self.sigmax * self.sigmay)
        if np.isinf(h3):
            return 0
        else:
            return h3

    def H4(self):
        "Sum of squares: variation."
        return self.sigmax ** 2

    def H5(self):
        "Inverse difference moment."
        t = 1 + toeplitz(self.levels) ** 2
        repeated = np.tile(t[np.newaxis], (self.nobjects, 1, 1))
        return (1.0 / repeated * self.P).sum(2).sum(1)

    def H6(self):
        "Sum average."
        if not hasattr(self, '_H6'):
            self._H6 = ((self.rlevels2 + 2) * self.p_xplusy).sum(1)
        return self._H6

    def H7(self):
        "Sum variance (error in Haralick's original paper here)."
        return (((self.rlevels2 + 2) - self.H6()) ** 2 * self.p_xplusy).sum(1)

    def H8(self):
        "Sum entropy."
        return -(self.p_xplusy * np.log(self.p_xplusy + self.eps)).sum(1)

    def H9(self):
        "Entropy."
        if not hasattr(self, '_H9'):
            self._H9 = -(self.P * np.log(self.P + self.eps)).sum(2).sum(1)
        return self._H9

    def H10(self):
        "Difference variance."
        c = (self.rlevels * self.p_xminusy).sum(1)
        e = self.rlevels - np.tile(c[np.newaxis], (self.nobjects,1))
        return (self.p_xminusy * e ** 2).sum(1)

    def H11(self):
        "Difference entropy."
        return -(self.p_xminusy * np.log(self.p_xminusy + self.eps)).sum(1)

    def H12(self):
        "Information measure of correlation 1."
        maxima = np.vstack((self.hx, self.hy)).max(0)
        return (self.H9() - self.hxy1) / maxima

    def H13(self):
        "Information measure of correlation 2."
        # An imaginary result has been encountered once in the Matlab
        # version.  The reason is unclear.
        return np.sqrt(1 - np.exp(-2 * (self.hxy2 - self.H9())))

    # There is a H14, max correlation coefficient, but we don't currently
    # use it.

    def all(self):
        return [self.H1(), self.H2(), self.H3(), self.H4(), self.H5(),
                self.H6(), self.H7(), self.H8(), self.H9(), self.H10(),
                self.H11(), self.H12(), self.H13()]

if False: # __name__ == '__main__':
    from PIL import Image
    import scipy.ndimage
    im = Image.open('/Users/ljosa/research/asr/ExampleSBSImages/Channel1-89-H-05.tif')
    im = im.convert('L')
    image = np.fromstring(im.tostring(), 'u1')
    image.shape = im.size[1], im.size[0]
    mask = image > 30
    labels = scipy.ndimage.label(mask)[0]
    h = haralick(image, labels, 3)
    print h

if __name__ == '__main__':
    gray = np.array([[0,0,1,1],[0,0,1,1],[0,2,2,2],[2,2,3,3]], dtype=float)
    labels = np.ones((4,4))
    labels = np.array([[0,0,0,0],[0,0,0,1],[0,0,1,1],[0,1,1,1]])
    P = cooccurrence(gray, labels, 1)

    